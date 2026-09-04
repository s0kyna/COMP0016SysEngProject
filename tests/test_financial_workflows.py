from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from models import (
    AgentAction, AgentActionStatus, BankRemittance, CaseEvidence, Customer,
    DunningAction, DunningActionStatus, GoodsReceivedNote, GRNStatus,
    HumanReviewCase, Invoice, InvoiceQAStatus, InvoiceStatus, OrderLineItem,
    OrderLineItemStatus, PaymentApplication, PurchaseOrder, PurchaseOrderStatus,
    RemittanceStatus,
)
from agents import invoice_qa, cash_application, dunning


def add_customer(s, cid, name):
    s.add(Customer(
        customer_id=cid,
        company_name=name,
        billing_email=f"billing{cid}@example.com",
        contact_email=f"finance{cid}@example.com",
        credit_limit=100000,
    ))


def add_invoice(s, invoice_id, po_id, grn_id, cid, amount=1000,
                status=InvoiceStatus.OUTSTANDING,
                qa=InvoiceQAStatus.PENDING,
                due_days=30):
    s.add(PurchaseOrder(
        po_id=po_id, customer_id=cid, order_date=datetime.utcnow(),
        expected_total=amount, status=PurchaseOrderStatus.FULFILLED,
    ))
    s.add(GoodsReceivedNote(
        grn_id=grn_id, po_id=po_id, delivery_date=datetime.utcnow(),
        received_by_signature="Tester", status=GRNStatus.FULL_DELIVERY,
    ))
    s.add(Invoice(
        invoice_id=invoice_id, po_id=po_id, grn_id=grn_id,
        issue_date=datetime.utcnow(),
        due_date=datetime.utcnow() + timedelta(days=due_days),
        total_amount=amount, qa_status=qa, status=status,
    ))


def test_invoice_deterministic_clean_match():
    evidence = {
        "invoice": {"po_id": "PO-1", "total_amount": 1000},
        "po": {"po_id": "PO-1", "expected_total": 1000},
        "grn": {"po_id": "PO-1"},
        "lines": [{
            "line_id": 1, "description": "Laptop",
            "ordered": 1, "received": 1, "billed": 1,
        }],
    }
    assert invoice_qa.deterministic_checks(evidence) == []


def test_invoice_deterministic_detects_quantity_and_total_mismatches():
    evidence = {
        "invoice": {"po_id": "PO-1", "total_amount": 1200},
        "po": {"po_id": "PO-1", "expected_total": 1000},
        "grn": {"po_id": "PO-1"},
        "lines": [{
            "line_id": 7, "description": "Monitor",
            "ordered": 10, "received": 8, "billed": 10,
        }],
    }
    issues = invoice_qa.deterministic_checks(evidence)
    assert any("differs from PO" in x for x in issues)
    assert any("ordered 10, received 8" in x for x in issues)
    assert any("received 8, billed 10" in x for x in issues)


def test_invoice_handover_policy_for_low_confidence():
    result = {
        "decision": "ACCEPT", "confidence": 0.70, "risk": "LOW"
    }
    result = invoice_qa.apply_handover_policy(result)
    assert result["human_review_required"] is True
    assert "Confidence below 0.80." in result["human_review_reasons"]


def test_invoice_handover_policy_for_high_risk():
    result = {
        "decision": "ACCEPT", "confidence": 0.95, "risk": "HIGH"
    }
    result = invoice_qa.apply_handover_policy(result)
    assert result["human_review_required"] is True


def test_invoice_parser_rejects_invalid_ai_decision():
    text = """DECISION: DELETE\nCATEGORY: X\nCONFIDENCE: 0.9\nRISK: LOW\nREASON: X\nMISSING_EVIDENCE: NONE\nRECOMMENDED_ACTION: X"""
    with pytest.raises(ValueError, match="Invalid AI decision"):
        invoice_qa.parse_response(text)


@pytest.mark.asyncio
async def test_invoice_clean_match_bypasses_ai(monkeypatch):
    monkeypatch.setattr(invoice_qa, "get_invoice_evidence", lambda _: {
        "invoice": {"po_id": "PO-1", "total_amount": 1000},
        "po": {"po_id": "PO-1", "expected_total": 1000},
        "grn": {"po_id": "PO-1"},
        "lines": [{"line_id": 1, "description": "X", "ordered": 1, "received": 1, "billed": 1}],
        "evidence": [],
    })
    ai = AsyncMock()
    monkeypatch.setattr(invoice_qa, "analyse_exception", ai)
    saved = {}
    monkeypatch.setattr(invoice_qa, "save_result", lambda i, r: saved.update(id=i, result=r))

    result = await invoice_qa.run_invoice_qa("INV-CLEAN")
    ai.assert_not_awaited()
    assert result["decision"] == "ACCEPT"
    assert saved["id"] == "INV-CLEAN"


def test_cash_exact_reference_match():
    case = {
        "amount": 1200,
        "raw_text": "Payment ref INV-42",
        "candidates": [
            {"invoice_id": "INV-42", "customer_id": 1, "customer_name": "ACME", "remaining": 1200},
            {"invoice_id": "INV-43", "customer_id": 1, "customer_name": "ACME", "remaining": 1200},
        ],
    }
    result = cash_application.deterministic_match(case)
    assert result["matched"] is True
    assert result["allocations"] == [{"invoice_id": "INV-42", "amount": 1200}]


def test_cash_ambiguous_equal_invoices_not_auto_matched():
    case = {
        "amount": 25000,
        "raw_text": "ACME Corporation September payment",
        "candidates": [
            {"invoice_id": "INV-A", "customer_id": 1, "customer_name": "ACME Corporation", "remaining": 25000},
            {"invoice_id": "INV-B", "customer_id": 1, "customer_name": "ACME Corporation", "remaining": 25000},
        ],
    }
    assert cash_application.deterministic_match(case) == {"matched": False}


def test_cash_unique_split_match():
    case = {
        "amount": 10000,
        "raw_text": "LIVE CASH LTD consolidated payment",
        "candidates": [
            {"invoice_id": "INV-1", "customer_id": 8, "customer_name": "Live Cash Ltd", "remaining": 7000},
            {"invoice_id": "INV-2", "customer_id": 8, "customer_name": "Live Cash Ltd", "remaining": 3000},
            {"invoice_id": "INV-X", "customer_id": 9, "customer_name": "Other Ltd", "remaining": 10000},
        ],
    }
    result = cash_application.deterministic_match(case)
    assert result["matched"] is True
    assert {x["invoice_id"] for x in result["allocations"]} == {"INV-1", "INV-2"}


def test_cash_save_match_persists_allocations_and_statuses(patch_db):
    s = patch_db()
    add_customer(s, 1, "Live Cash Ltd")
    add_invoice(s, "INV-1", "PO-1", "GRN-1", 1, 7000)
    add_invoice(s, "INV-2", "PO-2", "GRN-2", 1, 3000)
    s.add(BankRemittance(
        payment_id="PAY-1", payment_date=datetime.utcnow(), amount_received=10000,
        raw_bank_text="Live Cash Ltd consolidated payment",
        status=RemittanceStatus.UNPROCESSED,
    ))
    s.commit(); s.close()

    cash_application.save_match(
        "PAY-1",
        [{"invoice_id": "INV-1", "amount": 7000}, {"invoice_id": "INV-2", "amount": 3000}],
        1.0, "Unique split", automatic=True,
    )

    s = patch_db()
    p = s.query(BankRemittance).filter_by(payment_id="PAY-1").one()
    assert p.status == RemittanceStatus.MATCHED_AUTO
    assert p.matched_invoice_id is None
    assert s.query(PaymentApplication).filter_by(payment_id="PAY-1").count() == 2
    assert all(x.status == InvoiceStatus.PAID for x in s.query(Invoice).all())
    action = s.query(AgentAction).filter_by(entity_id="PAY-1").one()
    assert action.decision == "MATCH"
    assert action.status == AgentActionStatus.COMPLETED
    s.close()


def test_cash_human_review_is_duplicate_safe(patch_db):
    s = patch_db()
    s.add(BankRemittance(
        payment_id="PAY-X", payment_date=datetime.utcnow(), amount_received=100,
        raw_bank_text="unknown", status=RemittanceStatus.UNPROCESSED,
    ))
    s.commit(); s.close()

    cash_application.save_human_review("PAY-X", 0.4, "Ambiguous")
    cash_application.save_human_review("PAY-X", 0.4, "Ambiguous")

    s = patch_db()
    assert s.query(HumanReviewCase).filter_by(entity_id="PAY-X", status="OPEN").count() == 1
    assert s.query(AgentAction).filter_by(entity_id="PAY-X").count() == 2
    assert s.query(BankRemittance).filter_by(payment_id="PAY-X").one().status == RemittanceStatus.UNMATCHED_ESCALATED
    s.close()


@pytest.mark.asyncio
async def test_cash_live_deterministic_path_does_not_call_ai(monkeypatch):
    monkeypatch.setattr(cash_application, "get_payment_case", lambda _: {
        "payment_id": "PAY-LIVE-001", "amount": 10000,
        "raw_text": "LIVE CASH LTD consolidated payment",
        "candidates": [
            {"invoice_id": "INV-LIVE-101", "customer_id": 108, "customer_name": "Live Cash Ltd", "remaining": 7000},
            {"invoice_id": "INV-LIVE-102", "customer_id": 108, "customer_name": "Live Cash Ltd", "remaining": 3000},
        ],
    })
    ai = AsyncMock()
    monkeypatch.setattr(cash_application, "run_ai_match", ai)
    saved = {}
    monkeypatch.setattr(cash_application, "save_match", lambda **kw: saved.update(kw))

    result = await cash_application.run_cash_application("PAY-LIVE-001")
    ai.assert_not_awaited()
    assert result["decision"] == "MATCH"
    assert len(result["allocations"]) == 2
    assert saved["automatic"] is True


def test_dunning_deterministic_disputed_goes_to_human_review():
    case = {"invoice": {"status": InvoiceStatus.DISPUTED.value, "days_overdue": 20}}
    assert dunning.deterministic_check(case) == "HUMAN_REVIEW"


def test_dunning_not_due_requires_no_action():
    case = {"invoice": {"status": InvoiceStatus.OUTSTANDING.value, "days_overdue": 0}}
    assert dunning.deterministic_check(case) == "NOT_DUE"


def test_dunning_parser_validation():
    good = dunning.parse_response(
        "ACTION: WAIT\nCONFIDENCE: 0.9\nRISK: MEDIUM\nREASON: Promise received\nMESSAGE: NONE"
    )
    assert good["action"] == "WAIT"
    with pytest.raises(ValueError, match="Invalid action"):
        dunning.parse_response(
            "ACTION: DELETE\nCONFIDENCE: 0.9\nRISK: LOW\nREASON: X\nMESSAGE: NONE"
        )


@pytest.mark.asyncio
async def test_dunning_high_risk_ai_result_forces_human_review(monkeypatch):
    monkeypatch.setattr(dunning, "get_dunning_case", lambda _: {
        "invoice": {"status": InvoiceStatus.OVERDUE.value, "days_overdue": 40}
    })
    monkeypatch.setattr(dunning, "analyse_with_ai", AsyncMock(return_value={
        "action": "SEND_REMINDER", "confidence": 0.95, "risk": "HIGH",
        "reason": "High exposure", "message": "Pay now",
    }))
    saved = {}
    monkeypatch.setattr(dunning, "save_result", lambda i, r: saved.update(id=i, result=r.copy()))

    result = await dunning.run_dunning("INV-X")
    assert result["action"] == "HUMAN_REVIEW"
    assert saved["result"]["action"] == "HUMAN_REVIEW"


def test_azure_config_helper_reports_missing_variables(monkeypatch):
    for key in [
        "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_API_VERSION", "AZURE_OPENAI_DEPLOYMENT_NAME",
    ]:
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(RuntimeError, match="Azure OpenAI credentials are required"):
        cash_application.require_azure_config()
