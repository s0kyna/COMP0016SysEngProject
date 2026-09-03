# agents/invoice_qa.py
import os, asyncio
from dotenv import load_dotenv
from agent_framework import Agent
from agent_framework.openai import OpenAIChatCompletionClient
from db import get_session
from models import (
    Invoice, PurchaseOrder, GoodsReceivedNote, OrderLineItem, CaseEvidence,
    InvoiceQAStatus, AgentAction, AgentActionStatus, HumanReviewCase
)

load_dotenv()

INSTRUCTIONS = """
You are an AI Invoice Exception Analyst in an Order-to-Cash system.
Python has already performed deterministic accounting checks. You are only called when an exception exists.

You receive structured ERP data plus contextual evidence aggregated from systems such as ERP notes, warehouse records, emails and internal approvals.
You have no database access. Use ONLY supplied evidence and never invent facts.

Your job is to:
- interpret the business meaning and likely cause of discrepancies;
- distinguish errors from potentially legitimate exceptions;
- use free-text notes, approvals and contextual evidence;
- decide whether the case can be resolved automatically;
- identify missing evidence;
- escalate ambiguous, unsupported or risky cases to a human.

Return exactly:
DECISION: ACCEPT or HUMAN_REVIEW
CATEGORY: short category
CONFIDENCE: number from 0 to 1
RISK: LOW, MEDIUM, or HIGH
REASON: concise explanation
MISSING_EVIDENCE: missing information or NONE
RECOMMENDED_ACTION: concise next action
"""

def get_invoice_evidence(invoice_id):
    s = get_session()
    try:
        inv = s.query(Invoice).filter_by(invoice_id=invoice_id).first()
        if not inv: raise ValueError(f"Invoice {invoice_id} not found")
        po = s.query(PurchaseOrder).filter_by(po_id=inv.po_id).first()
        grn = s.query(GoodsReceivedNote).filter_by(grn_id=inv.grn_id).first()
        if not po or not grn: raise ValueError("Related PO or GRN not found")

        lines = s.query(OrderLineItem).filter_by(po_id=po.po_id).all()
        entities = [
            ("Invoice", inv.invoice_id),
            ("PurchaseOrder", po.po_id),
            ("GRN", grn.grn_id),
            ("Customer", str(po.customer_id))
        ]

        notes = []
        for entity_type, entity_id in entities:
            notes += s.query(CaseEvidence).filter_by(
                entity_type=entity_type, entity_id=entity_id
            ).all()

        return {
            "invoice": {
                "invoice_id": inv.invoice_id, "po_id": inv.po_id,
                "grn_id": inv.grn_id, "total_amount": float(inv.total_amount),
                "status": inv.status.value
            },
            "po": {
                "po_id": po.po_id, "customer_id": po.customer_id,
                "expected_total": float(po.expected_total), "status": po.status.value
            },
            "grn": {
                "grn_id": grn.grn_id, "po_id": grn.po_id,
                "status": grn.status.value
            },
            "lines": [{
                "line_id": x.line_id, "description": x.item_desc,
                "unit_price": float(x.unit_price), "ordered": x.ordered_qty,
                "received": x.received_qty, "billed": x.billed_qty,
                "status": x.status.value
            } for x in lines],
            "evidence": [{
                "entity_type": x.entity_type, "entity_id": x.entity_id,
                "source_system": x.source_system, "source": x.source,
                "type": x.evidence_type, "content": x.content
            } for x in notes]
        }
    finally:
        s.close()

def deterministic_checks(e):
    issues = []
    inv, po, grn = e["invoice"], e["po"], e["grn"]

    if inv["po_id"] != po["po_id"]: issues.append("Invoice references incorrect PO.")
    if grn["po_id"] != po["po_id"]: issues.append("GRN references incorrect PO.")

    diff = inv["total_amount"] - po["expected_total"]
    if abs(diff) > 0.01: issues.append(f"Invoice total differs from PO by £{diff:.2f}.")

    if not e["lines"]: issues.append("No order lines available.")

    for x in e["lines"]:
        if x["received"] != x["ordered"]:
            issues.append(f"Line {x['line_id']} ({x['description']}): ordered {x['ordered']}, received {x['received']}.")
        if x["billed"] != x["received"]:
            issues.append(f"Line {x['line_id']} ({x['description']}): received {x['received']}, billed {x['billed']}.")

    return issues

def format_case(e, issues):
    lines = "\n".join(
        f"- {x['line_id']} {x['description']}: £{x['unit_price']:.2f}, "
        f"ordered={x['ordered']}, received={x['received']}, billed={x['billed']}"
        for x in e["lines"]
    ) or "None"

    notes = "\n".join(
        f"- [{x['source_system']} / {x['source']} / {x['type']}] "
        f"{x['entity_type']} {x['entity_id']}: {x['content']}"
        for x in e["evidence"]
    ) or "None"

    return f"""
ERP DATA
Invoice: {e['invoice']}
Purchase Order: {e['po']}
GRN: {e['grn']}

ORDER LINES
{lines}

CONTEXTUAL EVIDENCE
{notes}

DETERMINISTIC EXCEPTIONS
{chr(10).join("- " + x for x in issues)}
"""

def parse_response(text):
    keys = {
        "DECISION": "decision", "CATEGORY": "category", "CONFIDENCE": "confidence",
        "RISK": "risk", "REASON": "reason", "MISSING_EVIDENCE": "missing_evidence",
        "RECOMMENDED_ACTION": "recommended_action"
    }
    result = {v: None for v in keys.values()}

    for line in text.splitlines():
        for label, key in keys.items():
            if line.strip().startswith(label + ":"):
                result[key] = line.split(":", 1)[1].strip()

    result["decision"] = (result["decision"] or "").upper()
    result["risk"] = (result["risk"] or "").upper()
    result["confidence"] = float(result["confidence"])

    if result["decision"] not in {"ACCEPT", "HUMAN_REVIEW"}:
        raise ValueError("Invalid AI decision")
    if result["risk"] not in {"LOW", "MEDIUM", "HIGH"}:
        raise ValueError("Invalid risk")
    if not 0 <= result["confidence"] <= 1:
        raise ValueError("Invalid confidence")

    return result

def apply_handover_policy(r):
    reasons = []

    if r["decision"] == "HUMAN_REVIEW":
        reasons.append("AI could not safely resolve the mismatch.")
    if r["confidence"] < 0.8:
        reasons.append("Confidence below 0.80.")
    if r["risk"] == "HIGH":
        reasons.append("High-risk case.")

    r["human_review_required"] = bool(reasons)
    r["human_review_reasons"] = reasons
    return r

def save_result(invoice_id, result):
    s = get_session()
    try:
        inv = s.query(Invoice).filter_by(invoice_id=invoice_id).first()
        inv.qa_status = (
            InvoiceQAStatus.MATCH
            if result["decision"] == "ACCEPT" and not result["human_review_required"]
            else InvoiceQAStatus.MISMATCH
        )

        s.add(AgentAction(
            agent_name="Invoice QA Agent",
            entity_type="Invoice",
            entity_id=invoice_id,
            action="Invoice QA",
            decision=result["decision"],
            reason=result["reason"],
            confidence=result["confidence"],
            status=AgentActionStatus.HUMAN_REVIEW
            if result["human_review_required"]
            else AgentActionStatus.COMPLETED
        ))

        if result["human_review_required"]:
            s.add(HumanReviewCase(
                review_type="INVOICE_QA_REVIEW",
                entity_type="Invoice",
                entity_id=invoice_id,
                reason=result["reason"],
                recommended_action=result["recommended_action"],
                status="OPEN"
            ))

        s.commit()
    except:
        s.rollback()
        raise
    finally:
        s.close()
        
async def analyse_exception(evidence, issues):
    client = OpenAIChatCompletionClient(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        model=os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"]
    )
    agent = Agent(client=client, name="InvoiceExceptionAnalyst", instructions=INSTRUCTIONS)
    response = await agent.run("Analyse this invoice exception:\n" + format_case(evidence, issues))
    print("\n===== AI ANALYSIS =====\n" + response.text)
    return parse_response(response.text)

async def run_invoice_qa(invoice_id):
    print(f"\n=== INVOICE QA: {invoice_id} ===")
    evidence = get_invoice_evidence(invoice_id)
    issues = deterministic_checks(evidence)

    if not issues:
        result = {
            "decision": "ACCEPT", "category": "CLEAN_MATCH", "confidence": 1.0,
            "risk": "LOW", "reason": "All deterministic checks passed.",
            "missing_evidence": "NONE", "recommended_action": "Approve invoice.",
            "human_review_required": False, "human_review_reasons": []
        }
        print("All deterministic checks passed; AI not required.")
    else:
        print("Exceptions:")
        for issue in issues: print(" -", issue)
        print(f"Contextual evidence found: {len(evidence['evidence'])}")
        result = apply_handover_policy(await analyse_exception(evidence, issues))

    save_result(invoice_id, result)
    return result

if __name__ == "__main__":
    r = asyncio.run(run_invoice_qa("INV-9901"))
    print("\n=== RESULT ===")
    print(f"Decision: {r['decision']}")
    print(f"Category: {r['category']}")
    print(f"Confidence: {r['confidence']}")
    print(f"Risk: {r['risk']}")
    print(f"Human review: {r['human_review_required']}")
    print(f"Reason: {r['reason']}")
    print(f"Missing evidence: {r['missing_evidence']}")
    print(f"Next action: {r['recommended_action']}")