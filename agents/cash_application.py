import os, asyncio
from dotenv import load_dotenv
from agent_framework import Agent
from agent_framework.openai import OpenAIChatCompletionClient
from db import get_session
from models import (
    BankRemittance, Invoice, PurchaseOrder, Customer, PaymentApplication,
    RemittanceStatus, InvoiceStatus, AgentAction, AgentActionStatus, HumanReviewCase
)

load_dotenv()

INSTRUCTIONS = """
You are an AI Cash Application Analyst in an Order-to-Cash system.

Python has already retrieved an incoming bank payment and candidate unpaid invoices.
You have no database access. Use ONLY the supplied evidence.

Your job is to determine whether the payment can be safely matched to one invoice.
Use payment amount, invoice references, customer/company names and free-text remittance information.

Do not invent missing information.
If multiple invoices are plausible or evidence is insufficient, require human review.

Return exactly:
DECISION: MATCH or HUMAN_REVIEW
INVOICE_ID: matching invoice ID or NONE
CONFIDENCE: number from 0 to 1
REASON: concise explanation
"""

def get_payment_case(payment_id):
    s = get_session()
    try:
        payment = s.query(BankRemittance).filter_by(payment_id=payment_id).first()
        if not payment: raise ValueError(f"Payment {payment_id} not found")

        invoices = s.query(Invoice).filter(
            Invoice.status.in_([InvoiceStatus.OUTSTANDING, InvoiceStatus.PARTIALLY_PAID])
        ).all()

        candidates = []
        for inv in invoices:
            po = s.query(PurchaseOrder).filter_by(po_id=inv.po_id).first()
            customer = s.query(Customer).filter_by(customer_id=po.customer_id).first() if po else None

            candidates.append({
                "invoice_id": inv.invoice_id,
                "amount": float(inv.total_amount),
                "customer": customer.company_name if customer else None
            })

        return {
            "payment": {
                "payment_id": payment.payment_id,
                "amount": float(payment.amount_received),
                "raw_text": payment.raw_bank_text
            },
            "candidates": candidates
        }
    finally:
        s.close()

def deterministic_match(case):
    p = case["payment"]
    text = p["raw_text"].replace("-", "").replace(" ", "").lower()

    matches = [
        x for x in case["candidates"]
        if abs(x["amount"] - p["amount"]) < 0.01
        and x["invoice_id"].replace("-", "").lower() in text
    ]

    return matches[0] if len(matches) == 1 else None

def format_case(case):
    candidates = "\n".join(
        f"- {x['invoice_id']}: £{x['amount']:.2f}, customer={x['customer']}"
        for x in case["candidates"]
    ) or "None"

    return f"""
PAYMENT
ID: {case['payment']['payment_id']}
Amount: £{case['payment']['amount']:.2f}
Bank text: {case['payment']['raw_text']}

CANDIDATE INVOICES
{candidates}
"""

def parse_response(text):
    result = {"decision": None, "invoice_id": None, "confidence": None, "reason": None}

    for line in text.splitlines():
        line = line.strip()
        if line.startswith("DECISION:"): result["decision"] = line.split(":", 1)[1].strip().upper()
        elif line.startswith("INVOICE_ID:"): result["invoice_id"] = line.split(":", 1)[1].strip()
        elif line.startswith("CONFIDENCE:"): result["confidence"] = float(line.split(":", 1)[1].strip())
        elif line.startswith("REASON:"): result["reason"] = line.split(":", 1)[1].strip()

    if result["decision"] not in {"MATCH", "HUMAN_REVIEW"}:
        raise ValueError("Invalid AI decision")
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

    agent = Agent(client=client, name="CashApplicationAgent", instructions=INSTRUCTIONS)
    response = await agent.run("Match this incoming payment:\n" + format_case(case))

    print("\n===== AI ANALYSIS =====\n" + response.text)
    return parse_response(response.text)

def save_result(payment_id, result):
    s = get_session()

    try:
        payment = s.query(BankRemittance).filter_by(payment_id=payment_id).first()

        if result["decision"] == "MATCH" and result["confidence"] >= 0.8:
            invoice = s.query(Invoice).filter_by(invoice_id=result["invoice_id"]).first()

            if not invoice:
                raise ValueError("AI returned an invoice that does not exist")

            s.add(PaymentApplication(
                payment_id=payment_id,
                invoice_id=invoice.invoice_id,
                matched_amount=payment.amount_received,
                match_confidence=result["confidence"],
                status="MATCHED"
            ))

            payment.status = RemittanceStatus.MATCHED_AUTO
            payment.matched_invoice_id = invoice.invoice_id
            invoice.status = InvoiceStatus.PAID
            action_status = AgentActionStatus.COMPLETED

        else:
            payment.status = RemittanceStatus.UNMATCHED_ESCALATED
            action_status = AgentActionStatus.HUMAN_REVIEW

            s.add(HumanReviewCase(
                review_type="CASH_APPLICATION_REVIEW",
                entity_type="BankRemittance",
                entity_id=payment_id,
                reason=result["reason"],
                recommended_action="Review candidate invoices and manually match the payment.",
                status="OPEN"
            ))

        s.add(AgentAction(
            agent_name="Cash Application Agent",
            entity_type="BankRemittance",
            entity_id=payment_id,
            action="Cash Application",
            decision=result["decision"],
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

async def run_cash_application(payment_id):
    print(f"\n=== CASH APPLICATION: {payment_id} ===")

    case = get_payment_case(payment_id)
    exact = deterministic_match(case)

    if exact:
        print(f"Exact deterministic match: {exact['invoice_id']}")
        result = {
            "decision": "MATCH",
            "invoice_id": exact["invoice_id"],
            "confidence": 1.0,
            "reason": "Payment amount and invoice reference matched exactly."
        }
    else:
        print("No unique deterministic match. Sending to AI...")
        result = await analyse_with_ai(case)

        if result["decision"] == "MATCH" and result["confidence"] < 0.8:
            result["decision"] = "HUMAN_REVIEW"

    save_result(payment_id, result)
    return result

if __name__ == "__main__":
    r = asyncio.run(run_cash_application("PAY-77881"))

    print("\n=== RESULT ===")
    print(f"Decision: {r['decision']}")
    print(f"Invoice: {r['invoice_id']}")
    print(f"Confidence: {r['confidence']}")
    print(f"Reason: {r['reason']}")