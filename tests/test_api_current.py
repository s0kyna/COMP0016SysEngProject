from datetime import datetime, timedelta

from fastapi.testclient import TestClient

import api
from models import (
    AgentAction, AgentActionStatus, BankRemittance, Customer, DunningAction,
    DunningActionStatus, GoodsReceivedNote, GRNStatus, HumanReviewCase,
    Invoice, InvoiceQAStatus, InvoiceStatus, PaymentApplication, PurchaseOrder,
    PurchaseOrderStatus, RemittanceStatus,
)


def add_customer(s, cid=1, name="ACME"):
    s.add(Customer(
        customer_id=cid, company_name=name,
        billing_email="billing@example.com", contact_email="finance@example.com",
        credit_limit=100000,
    ))


def add_invoice(s, iid="INV-1", poid="PO-1", gid="GRN-1", cid=1,
                amount=1000, status=InvoiceStatus.OUTSTANDING):
    s.add(PurchaseOrder(
        po_id=poid, customer_id=cid, order_date=datetime.utcnow(),
        expected_total=amount, status=PurchaseOrderStatus.FULFILLED,
    ))
    s.add(GoodsReceivedNote(
        grn_id=gid, po_id=poid, delivery_date=datetime.utcnow(),
        received_by_signature="Tester", status=GRNStatus.FULL_DELIVERY,
    ))
    s.add(Invoice(
        invoice_id=iid, po_id=poid, grn_id=gid,
        issue_date=datetime.utcnow(), due_date=datetime.utcnow() - timedelta(days=20),
        total_amount=amount, qa_status=InvoiceQAStatus.MISMATCH, status=status,
    ))


def test_get_reviews_returns_only_open_reviews(patch_db):
    s = patch_db()
    s.add_all([
        HumanReviewCase(review_type="INVOICE_QA_REVIEW", entity_type="Invoice", entity_id="INV-1", reason="x", status="OPEN"),
        HumanReviewCase(review_type="INVOICE_QA_REVIEW", entity_type="Invoice", entity_id="INV-2", reason="x", status="APPROVED"),
    ])
    s.commit(); s.close()
    client = TestClient(api.app)
    data = client.get("/reviews").json()
    assert [x["entity_id"] for x in data] == ["INV-1"]


def test_review_404(patch_db):
    client = TestClient(api.app)
    r = client.get("/reviews/999")
    assert r.status_code == 404


def test_invoice_review_approve_updates_invoice_and_resolution_metadata(patch_db):
    s = patch_db(); add_customer(s); add_invoice(s)
    review = HumanReviewCase(
        review_type="INVOICE_QA_REVIEW", entity_type="Invoice", entity_id="INV-1",
        reason="Mismatch", recommended_action="Review", status="OPEN",
    )
    s.add(review); s.commit(); rid = review.review_id; s.close()

    client = TestClient(api.app)
    r = client.post(f"/reviews/{rid}/resolve", json={"action": "APPROVE", "note": "Checked by finance"})
    assert r.status_code == 200

    s = patch_db()
    review = s.get(HumanReviewCase, rid)
    inv = s.query(Invoice).filter_by(invoice_id="INV-1").one()
    assert review.status == "APPROVED"
    assert review.resolved_at is not None
    assert review.resolution_action == "APPROVE"
    assert review.resolution_note == "Checked by finance"
    assert inv.qa_status == InvoiceQAStatus.MATCH
    s.close()


def test_cash_manual_allocation_rejects_wrong_total(patch_db):
    s = patch_db(); add_customer(s); add_invoice(s, amount=1000)
    s.add(BankRemittance(
        payment_id="PAY-1", payment_date=datetime.utcnow(), amount_received=1000,
        raw_bank_text="ACME", status=RemittanceStatus.UNMATCHED_ESCALATED,
    ))
    review = HumanReviewCase(
        review_type="CASH_APPLICATION_REVIEW", entity_type="BankRemittance",
        entity_id="PAY-1", reason="Ambiguous", status="OPEN",
    )
    s.add(review); s.commit(); rid = review.review_id; s.close()

    client = TestClient(api.app)
    r = client.post(f"/reviews/{rid}/resolve", json={
        "action": "MATCH", "allocations": [{"invoice_id": "INV-1", "amount": 900}]
    })
    assert r.status_code == 400
    assert "payment is £1000.00" in r.json()["detail"]


def test_cash_manual_allocation_rejects_overallocation(patch_db):
    s = patch_db(); add_customer(s); add_invoice(s, amount=500)
    s.add(BankRemittance(
        payment_id="PAY-1", payment_date=datetime.utcnow(), amount_received=1000,
        raw_bank_text="ACME", status=RemittanceStatus.UNMATCHED_ESCALATED,
    ))
    review = HumanReviewCase(
        review_type="CASH_APPLICATION_REVIEW", entity_type="BankRemittance",
        entity_id="PAY-1", reason="Ambiguous", status="OPEN",
    )
    s.add(review); s.commit(); rid = review.review_id; s.close()

    client = TestClient(api.app)
    r = client.post(f"/reviews/{rid}/resolve", json={
        "action": "MATCH", "allocations": [{"invoice_id": "INV-1", "amount": 1000}]
    })
    assert r.status_code == 400
    assert "exceeds remaining balance" in r.json()["detail"]


def test_cash_manual_match_persists_payment_application(patch_db):
    s = patch_db(); add_customer(s); add_invoice(s, amount=1000)
    s.add(BankRemittance(
        payment_id="PAY-1", payment_date=datetime.utcnow(), amount_received=1000,
        raw_bank_text="ACME", status=RemittanceStatus.UNMATCHED_ESCALATED,
    ))
    review = HumanReviewCase(
        review_type="CASH_APPLICATION_REVIEW", entity_type="BankRemittance",
        entity_id="PAY-1", reason="Ambiguous", status="OPEN",
    )
    s.add(review); s.commit(); rid = review.review_id; s.close()

    client = TestClient(api.app)
    r = client.post(f"/reviews/{rid}/resolve", json={
        "action": "MATCH", "allocations": [{"invoice_id": "INV-1", "amount": 1000}]
    })
    assert r.status_code == 200

    s = patch_db()
    assert s.query(PaymentApplication).filter_by(payment_id="PAY-1").count() == 1
    assert s.query(BankRemittance).filter_by(payment_id="PAY-1").one().status == RemittanceStatus.MATCHED_MANUAL
    assert s.query(Invoice).filter_by(invoice_id="INV-1").one().status == InvoiceStatus.PAID
    s.close()


def test_dunning_human_resolution_creates_history_action(patch_db):
    s = patch_db(); add_customer(s); add_invoice(s, status=InvoiceStatus.OVERDUE)
    review = HumanReviewCase(
        review_type="DUNNING_REVIEW", entity_type="Invoice", entity_id="INV-1",
        reason="Overdue", status="OPEN",
    )
    s.add(review); s.commit(); rid = review.review_id; s.close()

    client = TestClient(api.app)
    r = client.post(f"/reviews/{rid}/resolve", json={"action": "WAIT", "note": "Customer promised Friday"})
    assert r.status_code == 200

    s = patch_db()
    action = s.query(DunningAction).filter_by(invoice_id="INV-1").one()
    assert action.action_type == "WAIT"
    assert action.status == DunningActionStatus.PENDING
    assert action.message == "Customer promised Friday"
    s.close()


def test_agent_actions_endpoint(patch_db):
    s = patch_db()
    s.add(AgentAction(
        agent_name="Cash Application Agent", entity_type="BankRemittance",
        entity_id="PAY-1", action="Payment matching", decision="MATCH",
        reason="Exact match", confidence=1.0, status=AgentActionStatus.COMPLETED,
    ))
    s.commit(); s.close()
    client = TestClient(api.app)
    data = client.get("/agent-actions").json()
    assert data[0]["entity_id"] == "PAY-1"
    assert data[0]["decision"] == "MATCH"


def test_recent_cases_prefers_human_resolution_timestamp(patch_db):
    s = patch_db()
    old = datetime.utcnow() - timedelta(days=1)
    new = datetime.utcnow()
    s.add(HumanReviewCase(
        review_type="INVOICE_QA_REVIEW", entity_type="Invoice", entity_id="INV-1",
        reason="Mismatch", status="APPROVED", created_at=old,
        resolved_at=new, resolution_action="APPROVE",
    ))
    s.commit(); s.close()

    client = TestClient(api.app)
    item = next(x for x in client.get("/recent-cases").json() if x["entity_id"] == "INV-1")
    assert item["summary"] == "Human decision: Approve"
    assert item["status"] == "APPROVED"


def test_case_overview_payment_follows_only_confirmed_allocations(patch_db):
    s = patch_db()
    add_customer(s, 1, "ACME")
    add_invoice(s, "INV-1", "PO-1", "GRN-1", 1, 700)
    add_invoice(s, "INV-2", "PO-2", "GRN-2", 1, 300)
    s.add(BankRemittance(
        payment_id="PAY-1", payment_date=datetime.utcnow(), amount_received=1000,
        raw_bank_text="ACME consolidated", status=RemittanceStatus.MATCHED_AUTO,
    ))
    s.add_all([
        PaymentApplication(payment_id="PAY-1", invoice_id="INV-1", matched_amount=700, match_confidence=1.0, status="MATCHED_AUTO"),
        PaymentApplication(payment_id="PAY-1", invoice_id="INV-2", matched_amount=300, match_confidence=1.0, status="MATCHED_AUTO"),
    ])
    s.commit(); s.close()

    client = TestClient(api.app)
    data = client.get("/cases/PAY-1").json()
    assert set(data["related"]["invoices"]) == {"INV-1", "INV-2"}
    assert len(data["allocations"]) == 2
    assert any(item["type"] == "PAYMENT" and "split across 2 invoices" in item["title"] for item in data["timeline"])


def test_case_overview_unprocessed_payment_does_not_merge_candidate_invoices(patch_db):
    s = patch_db()
    add_customer(s, 1, "ACME")
    add_invoice(s, "INV-1", "PO-1", "GRN-1", 1, 1000)
    s.add(BankRemittance(
        payment_id="PAY-U", payment_date=datetime.utcnow(), amount_received=1000,
        raw_bank_text="ACME payment", status=RemittanceStatus.UNPROCESSED,
    ))
    s.commit(); s.close()

    client = TestClient(api.app)
    data = client.get("/cases/PAY-U").json()
    assert data["related"]["invoices"] == []
    assert data["allocations"] == []
