import os, asyncio
from datetime import datetime
from dotenv import load_dotenv
from agent_framework import Agent
from agent_framework.openai import OpenAIChatCompletionClient
from db import get_session
from models import (
    Invoice, PurchaseOrder, Customer, DunningAction, CaseEvidence,
    InvoiceStatus, DunningActionStatus, AgentAction, AgentActionStatus,
    HumanReviewCase
)

load_dotenv()

INSTRUCTIONS = """
You are an AI Dunning Analyst in an Order-to-Cash system.

Python has already calculated objective facts such as days overdue and previous reminders.
You receive invoice, customer, dunning history and contextual evidence.
You have no database access. Use ONLY supplied evidence.

Your job is to decide the next collections action.

Use business context such as:
- days overdue;
- amount owed;
- previous reminders;
- previous payment promises;
- customer correspondence;
- whether the invoice is disputed;
- whether there is a credible reason to wait.

Return exactly:
ACTION: SEND_REMINDER, WAIT, or HUMAN_REVIEW
CONFIDENCE: number from 0 to 1
RISK: LOW, MEDIUM, or HIGH
REASON: concise explanation
MESSAGE: reminder text if SEND_REMINDER, otherwise NONE
"""

def get_dunning_case(invoice_id):
    s = get_session()
    try:
        inv = s.query(Invoice).filter_by(invoice_id=invoice_id).first()
        if not inv: raise ValueError(f"Invoice {invoice_id} not found")

        po = s.query(PurchaseOrder).filter_by(po_id=inv.po_id).first()
        customer = s.query(Customer).filter_by(customer_id=po.customer_id).first()
        history = s.query(DunningAction).filter_by(invoice_id=invoice_id).all()

        evidence = []
        entities = [
            ("Invoice", inv.invoice_id),
            ("Customer", str(customer.customer_id))
        ]
        for entity_type, entity_id in entities:
            evidence += s.query(CaseEvidence).filter_by(
                entity_type=entity_type, entity_id=entity_id
            ).all()

        days_overdue = max(0, (datetime.utcnow() - inv.due_date).days)

        return {
            "invoice": {
                "invoice_id": inv.invoice_id,
                "amount": float(inv.total_amount),
                "status": inv.status.value,
                "due_date": inv.due_date.isoformat(),
                "days_overdue": days_overdue
            },
            "customer": {
                "customer_id": customer.customer_id,
                "company_name": customer.company_name,
                "billing_email": customer.billing_email
            },
            "history": [{
                "action_date": x.action_date.isoformat(),
                "action_type": x.action_type,
                "message": x.message,
                "status": x.status.value
            } for x in history],
            "evidence": [{
                "source_system": x.source_system,
                "source": x.source,
                "type": x.evidence_type,
                "content": x.content
            } for x in evidence]
        }
    finally:
        s.close()

def deterministic_check(case):
    inv = case["invoice"]

    if inv["status"] == InvoiceStatus.DISPUTED.value:
        return "HUMAN_REVIEW"

    if inv["days_overdue"] <= 0:
        return "NOT_DUE"

    return None

def format_case(c):
    history = "\n".join(
        f"- {x['action_date']}: {x['action_type']} - {x['message']}"
        for x in c["history"]
    ) or "None"

    evidence = "\n".join(
        f"- [{x['source_system']} / {x['source']} / {x['type']}] {x['content']}"
        for x in c["evidence"]
    ) or "None"

    return f"""
INVOICE
{c['invoice']}

CUSTOMER
{c['customer']}

PREVIOUS DUNNING ACTIONS
{history}

CONTEXTUAL EVIDENCE
{evidence}
"""

def parse_response(text):
    result = {
        "action": None, "confidence": None,
        "risk": None, "reason": None, "message": None
    }

    for line in text.splitlines():
        line = line.strip()
        if line.startswith("ACTION:"): result["action"] = line.split(":",1)[1].strip().upper()
        elif line.startswith("CONFIDENCE:"): result["confidence"] = float(line.split(":",1)[1].strip())
        elif line.startswith("RISK:"): result["risk"] = line.split(":",1)[1].strip().upper()
        elif line.startswith("REASON:"): result["reason"] = line.split(":",1)[1].strip()
        elif line.startswith("MESSAGE:"): result["message"] = line.split(":",1)[1].strip()

    if result["action"] not in {"SEND_REMINDER", "WAIT", "HUMAN_REVIEW"}:
        raise ValueError("Invalid action")
    if result["risk"] not in {"LOW", "MEDIUM", "HIGH"}:
        raise ValueError("Invalid risk")
    if not 0 <= result["confidence"] <= 1:
        raise ValueError("Invalid confidence")

    return result

async def analyse_with_ai(case):
    client = OpenAIChatCompletionClient(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        model=os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"]
    )

    agent = Agent(client=client, name="DunningAgent", instructions=INSTRUCTIONS)
    response = await agent.run("Decide the next dunning action:\n" + format_case(case))
    print("\n===== AI ANALYSIS =====\n" + response.text)
    return parse_response(response.text)

def save_result(invoice_id, result):
    s = get_session()
    try:
        inv = s.query(Invoice).filter_by(invoice_id=invoice_id).first()
        po = s.query(PurchaseOrder).filter_by(po_id=inv.po_id).first()

        if result["action"] == "SEND_REMINDER":
            s.add(DunningAction(
                invoice_id=invoice_id,
                customer_id=po.customer_id,
                action_type="REMINDER",
                message=result["message"],
                status=DunningActionStatus.SENT
            ))
            action_status = AgentActionStatus.COMPLETED

        elif result["action"] == "WAIT":
            s.add(DunningAction(
                invoice_id=invoice_id,
                customer_id=po.customer_id,
                action_type="WAIT",
                message=result["reason"],
                status=DunningActionStatus.PENDING
            ))
            action_status = AgentActionStatus.COMPLETED

        else:
            s.add(HumanReviewCase(
                review_type="DUNNING_REVIEW",
                entity_type="Invoice",
                entity_id=invoice_id,
                reason=result["reason"],
                recommended_action="Review overdue account and determine next collections action.",
                status="OPEN"
            ))
            action_status = AgentActionStatus.HUMAN_REVIEW

        s.add(AgentAction(
            agent_name="Dunning Agent",
            entity_type="Invoice",
            entity_id=invoice_id,
            action="Dunning",
            decision=result["action"],
            reason=result["reason"],
            confidence=result["confidence"],
            status=action_status
        ))

        s.commit()
    except:
        s.rollback()
        raise
    finally:
        s.close()

async def run_dunning(invoice_id):
    print(f"\n=== DUNNING: {invoice_id} ===")
    case = get_dunning_case(invoice_id)
    deterministic = deterministic_check(case)

    if deterministic == "NOT_DUE":
        print("Invoice is not overdue. No action needed.")
        return {"action": "NO_ACTION"}

    if deterministic == "HUMAN_REVIEW":
        result = {
            "action": "HUMAN_REVIEW",
            "confidence": 1.0,
            "risk": "HIGH",
            "reason": "Invoice is disputed and should not be automatically chased.",
            "message": "NONE"
        }
    else:
        result = await analyse_with_ai(case)

        if result["confidence"] < 0.8 or result["risk"] == "HIGH":
            result["action"] = "HUMAN_REVIEW"

    save_result(invoice_id, result)
    return result

if __name__ == "__main__":
    r = asyncio.run(run_dunning("INV-9901"))
    print("\n=== RESULT ===")
    for k, v in r.items():
        print(f"{k}: {v}")