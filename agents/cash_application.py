import asyncio
import os
import re
from itertools import combinations

from dotenv import load_dotenv
from agent_framework import Agent
from agent_framework.openai import OpenAIChatCompletionClient

from db import get_session
from models import (
    BankRemittance, Invoice, PurchaseOrder, Customer, PaymentApplication,
    HumanReviewCase, AgentAction, InvoiceStatus, RemittanceStatus,
    AgentActionStatus
)

load_dotenv()

def require_azure_config():
    required = [
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_API_VERSION",
        "AZURE_OPENAI_DEPLOYMENT_NAME",
    ]

    missing = [
        key for key in required
        if not os.getenv(key)
    ]

    if missing:
        raise RuntimeError(
            "Azure OpenAI credentials are required for this case. "
            "Missing: " + ", ".join(missing)
        )

CASH_APPLICATION_INSTRUCTIONS = """
You are a Cash Application Agent for an Order-to-Cash process.

Your task is to determine whether an incoming bank remittance can be safely
matched to one outstanding invoice.

Use the payment amount, bank text, invoice IDs, customer names and remaining
balances.

If there is one clearly supported invoice, return MATCH.
If multiple invoices are equally plausible, evidence is insufficient, or the
payment appears to require a split that cannot be determined safely, return
HUMAN_REVIEW.

Never guess.

Return exactly:
DECISION: MATCH or HUMAN_REVIEW
INVOICE_ID: invoice id or NONE
CONFIDENCE: number from 0 to 1
REASON: short explanation
"""

def _normalize(value):
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())

def _remaining_balance(session, invoice):
    applications = session.query(PaymentApplication).filter_by(
        invoice_id=invoice.invoice_id
    ).all()
    applied = sum(float(x.matched_amount) for x in applications)
    return max(0, float(invoice.total_amount) - applied)

def get_payment_case(payment_id):
    session = get_session()
    try:
        payment = session.query(BankRemittance).filter_by(
            payment_id=payment_id
        ).first()
        if payment is None:
            raise ValueError(f"Payment {payment_id} was not found.")

        invoices = session.query(Invoice).filter(
            Invoice.status.in_([
                InvoiceStatus.OUTSTANDING,
                InvoiceStatus.PARTIALLY_PAID
            ])
        ).all()

        candidates = []
        for invoice in invoices:
            po = session.query(PurchaseOrder).filter_by(
                po_id=invoice.po_id
            ).first()
            customer = session.query(Customer).filter_by(
                customer_id=po.customer_id
            ).first()

            candidates.append({
                "invoice_id": invoice.invoice_id,
                "invoice": invoice,
                "customer_id": customer.customer_id,
                "customer_name": customer.company_name,
                "remaining": _remaining_balance(session, invoice)
            })

        return {
            "payment_id": payment.payment_id,
            "amount": float(payment.amount_received),
            "raw_text": payment.raw_bank_text or "",
            "candidates": candidates
        }
    finally:
        session.close()

def deterministic_match(case):
    amount = case["amount"]
    text = _normalize(case["raw_text"])
    candidates = case["candidates"]

    # 1. Exact invoice reference + exact remaining balance.
    referenced = [
        x for x in candidates
        if _normalize(x["invoice_id"]) in text
        and abs(x["remaining"] - amount) <= 0.01
    ]
    if len(referenced) == 1:
        x = referenced[0]
        return {
            "matched": True,
            "allocations": [{
                "invoice_id": x["invoice_id"],
                "amount": x["remaining"]
            }],
            "confidence": 1.0,
            "reason": (
                f"Bank text explicitly references {x['invoice_id']} and the "
                "payment exactly matches its remaining balance."
            )
        }

    # 2. Restrict deterministic amount matching to a customer explicitly
    # identified in the bank text.
    customer_ids = {
        x["customer_id"] for x in candidates
        if _normalize(x["customer_name"]) in text
    }
    if not customer_ids:
        return {"matched": False}

    related = [x for x in candidates if x["customer_id"] in customer_ids]

    # One unique invoice for that customer matches the payment exactly.
    singles = [x for x in related if abs(x["remaining"] - amount) <= 0.01]
    if len(singles) == 1:
        x = singles[0]
        return {
            "matched": True,
            "allocations": [{
                "invoice_id": x["invoice_id"],
                "amount": x["remaining"]
            }],
            "confidence": 1.0,
            "reason": (
                f"{x['customer_name']} is identified in the bank text and "
                f"{x['invoice_id']} is the unique outstanding invoice whose "
                "remaining balance equals the payment."
            )
        }

    # 3. Unique exact split across 2 or 3 invoices for the same customer.
    matches = []
    for size in range(2, min(3, len(related)) + 1):
        for combo in combinations(related, size):
            total = sum(x["remaining"] for x in combo)
            if abs(total - amount) <= 0.01:
                matches.append(combo)

    if len(matches) == 1:
        combo = matches[0]
        allocations = [
            {
                "invoice_id": x["invoice_id"],
                "amount": x["remaining"]
            }
            for x in combo
        ]
        ids = ", ".join(x["invoice_id"] for x in combo)
        return {
            "matched": True,
            "allocations": allocations,
            "confidence": 1.0,
            "reason": (
                f"The payment identifies {combo[0]['customer_name']} and "
                f"there is exactly one combination of outstanding invoices "
                f"whose balances equal the payment: {ids}."
            )
        }

    return {"matched": False}

def _format_case_for_ai(case):
    lines = [
        f"Payment ID: {case['payment_id']}",
        f"Amount: £{case['amount']:.2f}",
        f"Bank text: {case['raw_text']}",
        "",
        "Candidate invoices:"
    ]

    for x in case["candidates"]:
        lines.append(
            f"- {x['invoice_id']} | customer={x['customer_name']} | "
            f"remaining=£{x['remaining']:.2f}"
        )

    return "\n".join(lines)

def _parse_response(text):
    result = {
        "decision": "HUMAN_REVIEW",
        "invoice_id": None,
        "confidence": 0.0,
        "reason": "Agent response could not be parsed safely."
    }

    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().upper()
        value = value.strip()

        if key == "DECISION":
            result["decision"] = value.upper()
        elif key == "INVOICE_ID":
            result["invoice_id"] = None if value.upper() == "NONE" else value
        elif key == "CONFIDENCE":
            try:
                result["confidence"] = float(value)
            except ValueError:
                pass
        elif key == "REASON":
            result["reason"] = value

    return result

async def run_ai_match(case):
    require_azure_config()
    client = OpenAIChatCompletionClient(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        model=os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"]
    )

    agent = Agent(
        client=client,
        name="CashApplicationAgent",
        instructions=CASH_APPLICATION_INSTRUCTIONS
    )

    response = await agent.run(
        "Review this bank remittance and choose a safe match.\n\n"
        + _format_case_for_ai(case)
    )
    return _parse_response(response.text)

def save_match(payment_id, allocations, confidence, reason, automatic=True):
    session = get_session()
    try:
        payment = session.query(BankRemittance).filter_by(
            payment_id=payment_id
        ).first()
        if payment is None:
            raise ValueError(f"Payment {payment_id} was not found.")

        for allocation in allocations:
            invoice = session.query(Invoice).filter_by(
                invoice_id=allocation["invoice_id"]
            ).first()
            if invoice is None:
                raise ValueError(
                    f"Invoice {allocation['invoice_id']} was not found."
                )

            previous = session.query(PaymentApplication).filter_by(
                invoice_id=invoice.invoice_id
            ).all()
            already_paid = sum(float(x.matched_amount) for x in previous)

            session.add(PaymentApplication(
                payment_id=payment.payment_id,
                invoice_id=invoice.invoice_id,
                matched_amount=allocation["amount"],
                match_confidence=confidence,
                status="MATCHED_AUTO" if automatic else "MATCHED_MANUAL"
            ))

            new_paid = already_paid + allocation["amount"]
            invoice.status = (
                InvoiceStatus.PAID
                if new_paid >= float(invoice.total_amount) - 0.01
                else InvoiceStatus.PARTIALLY_PAID
            )

        payment.status = (
            RemittanceStatus.MATCHED_AUTO
            if automatic else RemittanceStatus.MATCHED_MANUAL
        )
        payment.matched_invoice_id = (
            allocations[0]["invoice_id"] if len(allocations) == 1 else None
        )

        session.add(AgentAction(
            agent_name="Cash Application Agent",
            entity_type="BankRemittance",
            entity_id=payment_id,
            action="Payment matching",
            decision="MATCH",
            reason=reason,
            confidence=confidence,
            status=AgentActionStatus.COMPLETED
        ))

        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

def save_human_review(payment_id, confidence, reason):
    session = get_session()
    try:
        payment = session.query(BankRemittance).filter_by(
            payment_id=payment_id
        ).first()
        if payment is None:
            raise ValueError(f"Payment {payment_id} was not found.")

        payment.status = RemittanceStatus.UNMATCHED_ESCALATED

        existing = session.query(HumanReviewCase).filter_by(
            review_type="CASH_APPLICATION_REVIEW",
            entity_type="BankRemittance",
            entity_id=payment_id,
            status="OPEN"
        ).first()

        if existing is None:
            session.add(HumanReviewCase(
                review_type="CASH_APPLICATION_REVIEW",
                entity_type="BankRemittance",
                entity_id=payment_id,
                reason=reason,
                recommended_action=(
                    "Review the candidate invoices and allocate the payment manually."
                ),
                status="OPEN"
            ))

        session.add(AgentAction(
            agent_name="Cash Application Agent",
            entity_type="BankRemittance",
            entity_id=payment_id,
            action="Payment matching",
            decision="HUMAN_REVIEW",
            reason=reason,
            confidence=confidence,
            status=AgentActionStatus.HUMAN_REVIEW
        ))

        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

async def run_cash_application(payment_id):
    print("\n========================================")
    print("       CASH APPLICATION WORKFLOW")
    print("========================================")

    case = get_payment_case(payment_id)

    print("\n[1] Running deterministic payment checks...")
    deterministic = deterministic_match(case)

    if deterministic["matched"]:
        allocations = deterministic["allocations"]
        save_match(
            payment_id=payment_id,
            allocations=allocations,
            confidence=deterministic["confidence"],
            reason=deterministic["reason"],
            automatic=True
        )

        print("    Payment matched automatically.")
        return {
            "decision": "MATCH",
            "invoice_id": (
                allocations[0]["invoice_id"]
                if len(allocations) == 1 else None
            ),
            "allocations": allocations,
            "confidence": deterministic["confidence"],
            "reason": deterministic["reason"]
        }

    print("    Deterministic match not possible.")
    print("\n[2] Sending ambiguous remittance to AI...")
    result = await run_ai_match(case)

    # A low-confidence match is not allowed to update financial records.
    if (
        result["decision"] != "MATCH"
        or not result["invoice_id"]
        or result["confidence"] < 0.8
    ):
        result["decision"] = "HUMAN_REVIEW"
        save_human_review(
            payment_id,
            result["confidence"],
            result["reason"]
        )
        return result

    candidate = next(
        (
            x for x in case["candidates"]
            if x["invoice_id"] == result["invoice_id"]
        ),
        None
    )

    if candidate is None or abs(candidate["remaining"] - case["amount"]) > 0.01:
        result["decision"] = "HUMAN_REVIEW"
        result["reason"] = (
            "AI proposed a match that does not safely reconcile to the "
            "payment amount. Human review is required."
        )
        save_human_review(
            payment_id,
            result["confidence"],
            result["reason"]
        )
        return result

    allocations = [{
        "invoice_id": candidate["invoice_id"],
        "amount": candidate["remaining"]
    }]

    save_match(
        payment_id=payment_id,
        allocations=allocations,
        confidence=result["confidence"],
        reason=result["reason"],
        automatic=True
    )

    result["allocations"] = allocations
    return result

if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print(
            "Usage: python -m agents.cash_application <payment_id>"
        )
        sys.exit(1)

    payment_id = sys.argv[1]

    result = asyncio.run(
        run_cash_application(payment_id)
    )

    print("\n========================================")
    print("           FINAL RESULT")
    print("========================================")
    print(result)