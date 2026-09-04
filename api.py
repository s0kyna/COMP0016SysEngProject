from datetime import datetime
from itertools import combinations
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from db import get_session
from models import (
    HumanReviewCase, Invoice, BankRemittance, PaymentApplication,
    InvoiceStatus, InvoiceQAStatus, RemittanceStatus, PurchaseOrder,
    GoodsReceivedNote, OrderLineItem, CaseEvidence, AgentAction,
    Customer, DunningAction, DunningActionStatus
)

app = FastAPI(title="O2C Agents API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

class Allocation(BaseModel):
    invoice_id: str
    amount: float

class ReviewAction(BaseModel):
    action: str
    invoice_id: str | None = None
    allocations: list[Allocation] | None = None
    note: str | None = None

def _invoice_balance(s, invoice):
    applied = s.query(PaymentApplication).filter_by(invoice_id=invoice.invoice_id).all()
    already_applied = sum(float(x.matched_amount) for x in applied)
    return already_applied, max(0, float(invoice.total_amount) - already_applied)

def _candidate_invoices_for_payment(s, payment):
    invoices = s.query(Invoice).filter(
        Invoice.status.in_([InvoiceStatus.OUTSTANDING, InvoiceStatus.PARTIALLY_PAID])
    ).all()
    text = (payment.raw_bank_text or "").lower()
    customer_matches = []
    for customer in s.query(Customer).all():
        if customer.company_name.lower() in text:
            customer_matches.append(customer.customer_id)
    if customer_matches:
        po_ids = [x.po_id for x in s.query(PurchaseOrder).filter(
            PurchaseOrder.customer_id.in_(customer_matches)
        ).all()]
        invoices = [x for x in invoices if x.po_id in po_ids]
    amount = float(payment.amount_received)
    exact = [x for x in invoices if abs(_invoice_balance(s, x)[1] - amount) <= 0.01]
    if exact:
        return exact
    pair_ids = set()
    for a, b in combinations(invoices, 2):
        if abs((_invoice_balance(s, a)[1] + _invoice_balance(s, b)[1]) - amount) <= 0.01:
            pair_ids.update([a.invoice_id, b.invoice_id])
    if pair_ids:
        return [x for x in invoices if x.invoice_id in pair_ids]
    return sorted(invoices, key=lambda x: abs(_invoice_balance(s, x)[1] - amount))[:4]

@app.get("/reviews")
def get_reviews(review_type: str | None = None):
    s = get_session()
    try:
        q = s.query(HumanReviewCase).filter_by(status="OPEN")
        if review_type:
            q = q.filter_by(review_type=review_type)
        return [{
            "review_id": r.review_id,
            "review_type": r.review_type,
            "entity_type": r.entity_type,
            "entity_id": r.entity_id,
            "reason": r.reason,
            "recommended_action": r.recommended_action,
            "status": r.status,
            "created_at": r.created_at
        } for r in q.order_by(HumanReviewCase.created_at.desc()).all()]
    finally:
        s.close()

@app.get("/reviews/{review_id}")
def get_review(review_id: int):
    s = get_session()
    try:
        r = s.query(HumanReviewCase).filter_by(review_id=review_id).first()
        if not r:
            raise HTTPException(404, "Review not found")
        return {
            "review_id": r.review_id,
            "review_type": r.review_type,
            "entity_type": r.entity_type,
            "entity_id": r.entity_id,
            "reason": r.reason,
            "recommended_action": r.recommended_action,
            "status": r.status,
            "created_at": r.created_at
        }
    finally:
        s.close()

@app.post("/reviews/{review_id}/resolve")
def resolve_review(review_id: int, data: ReviewAction):
    s = get_session()
    try:
        review = s.query(HumanReviewCase).filter_by(review_id=review_id).first()
        if not review:
            raise HTTPException(404, "Review not found")
        if review.status != "OPEN":
            raise HTTPException(400, "Review already resolved")
        action = data.action.upper()

        if review.review_type == "INVOICE_QA_REVIEW":
            invoice = s.query(Invoice).filter_by(invoice_id=review.entity_id).first()
            if not invoice:
                raise HTTPException(404, "Invoice not found")
            if action == "APPROVE":
                invoice.qa_status = InvoiceQAStatus.MATCH
                review.status = "APPROVED"
            elif action == "REJECT":
                invoice.qa_status = InvoiceQAStatus.MISMATCH
                review.status = "REJECTED"
            else:
                raise HTTPException(400, "Use APPROVE or REJECT")

        elif review.review_type == "CASH_APPLICATION_REVIEW":
            payment = s.query(BankRemittance).filter_by(payment_id=review.entity_id).first()
            if not payment:
                raise HTTPException(404, "Payment not found")
            if action == "MATCH":
                if not data.allocations:
                    raise HTTPException(400, "At least one allocation is required")
                total_allocated = sum(x.amount for x in data.allocations)
                if total_allocated <= 0:
                    raise HTTPException(400, "Allocation must be greater than zero")
                if abs(total_allocated - float(payment.amount_received)) > 0.01:
                    raise HTTPException(400, f"Allocated £{total_allocated:.2f}, but payment is £{float(payment.amount_received):.2f}")
                used = set()
                for allocation in data.allocations:
                    if allocation.invoice_id in used:
                        raise HTTPException(400, "Duplicate invoice allocation")
                    used.add(allocation.invoice_id)
                    invoice = s.query(Invoice).filter_by(invoice_id=allocation.invoice_id).first()
                    if not invoice:
                        raise HTTPException(404, f"Invoice {allocation.invoice_id} not found")
                    already_paid, remaining = _invoice_balance(s, invoice)
                    if allocation.amount > remaining + 0.01:
                        raise HTTPException(400, f"Allocation exceeds remaining balance for {invoice.invoice_id}")
                    s.add(PaymentApplication(
                        payment_id=payment.payment_id,
                        invoice_id=invoice.invoice_id,
                        matched_amount=allocation.amount,
                        match_confidence=None,
                        status="MATCHED_MANUAL"
                    ))
                    invoice.status = InvoiceStatus.PAID if already_paid + allocation.amount >= float(invoice.total_amount) - 0.01 else InvoiceStatus.PARTIALLY_PAID
                payment.status = RemittanceStatus.MATCHED_MANUAL
                payment.matched_invoice_id = data.allocations[0].invoice_id if len(data.allocations) == 1 else None
                review.status = "MATCHED"
            elif action == "LEAVE_UNMATCHED":
                review.status = "UNMATCHED"
            else:
                raise HTTPException(400, "Use MATCH or LEAVE_UNMATCHED")

        elif review.review_type == "DUNNING_REVIEW":
            if action not in {"SEND_REMINDER", "WAIT", "ESCALATE"}:
                raise HTTPException(400, "Use SEND_REMINDER, WAIT or ESCALATE")
            if action == "SEND_REMINDER":
                invoice = s.query(Invoice).filter_by(invoice_id=review.entity_id).first()
                if not invoice:
                    raise HTTPException(404, "Invoice not found")
                po = s.query(PurchaseOrder).filter_by(po_id=invoice.po_id).first()
                s.add(DunningAction(
                    invoice_id=invoice.invoice_id,
                    customer_id=po.customer_id,
                    action_date=datetime.utcnow(),
                    action_type="REMINDER",
                    message=data.note or "Payment reminder approved by human reviewer.",
                    status=DunningActionStatus.SENT
                ))
            review.status = action
        else:
            raise HTTPException(400, "Unknown review type")

        s.commit()
        return {"review_id": review.review_id, "status": review.status}
    except:
        s.rollback()
        raise
    finally:
        s.close()

@app.get("/reviews/{review_id}/cash-details")
def get_cash_review_details(review_id: int):
    s = get_session()
    try:
        review = s.query(HumanReviewCase).filter_by(review_id=review_id).first()
        if not review:
            raise HTTPException(404, "Review not found")
        if review.review_type != "CASH_APPLICATION_REVIEW":
            raise HTTPException(400, "Not a cash application review")
        payment = s.query(BankRemittance).filter_by(payment_id=review.entity_id).first()
        if not payment:
            raise HTTPException(404, "Payment not found")
        candidates = []
        for invoice in _candidate_invoices_for_payment(s, payment):
            po = s.query(PurchaseOrder).filter_by(po_id=invoice.po_id).first()
            customer = s.query(Customer).filter_by(customer_id=po.customer_id).first()
            already_applied, remaining = _invoice_balance(s, invoice)
            candidates.append({
                "invoice_id": invoice.invoice_id,
                "amount": float(invoice.total_amount),
                "already_applied": already_applied,
                "remaining": remaining,
                "customer": customer.company_name,
                "status": invoice.status.value
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

@app.get("/reviews/{review_id}/invoice-qa-details")
def get_invoice_qa_details(review_id: int):
    s = get_session()
    try:
        review = s.query(HumanReviewCase).filter_by(review_id=review_id).first()
        if not review:
            raise HTTPException(404, "Review not found")
        if review.review_type != "INVOICE_QA_REVIEW":
            raise HTTPException(400, "Not an invoice QA review")
        invoice = s.query(Invoice).filter_by(invoice_id=review.entity_id).first()
        if not invoice:
            raise HTTPException(404, "Invoice not found")
        po = s.query(PurchaseOrder).filter_by(po_id=invoice.po_id).first()
        grn = s.query(GoodsReceivedNote).filter_by(grn_id=invoice.grn_id).first()
        lines = s.query(OrderLineItem).filter_by(po_id=invoice.po_id).all()
        entity_pairs = [
            ("Invoice", invoice.invoice_id), ("PurchaseOrder", po.po_id),
            ("GRN", grn.grn_id), ("Customer", str(po.customer_id))
        ]
        evidence = []
        for entity_type, entity_id in entity_pairs:
            evidence += s.query(CaseEvidence).filter_by(entity_type=entity_type, entity_id=entity_id).all()
        return {
            "invoice": {"invoice_id": invoice.invoice_id, "total_amount": float(invoice.total_amount), "status": invoice.status.value, "qa_status": invoice.qa_status.value},
            "purchase_order": {"po_id": po.po_id, "expected_total": float(po.expected_total), "status": po.status.value},
            "grn": {"grn_id": grn.grn_id, "status": grn.status.value},
            "lines": [{"line_id": x.line_id, "description": x.item_desc, "unit_price": float(x.unit_price), "ordered": x.ordered_qty, "received": x.received_qty, "billed": x.billed_qty} for x in lines],
            "evidence": [{"source_system": x.source_system, "source": x.source, "type": x.evidence_type, "content": x.content} for x in evidence]
        }
    finally:
        s.close()

@app.get("/reviews/{review_id}/dunning-details")
def get_dunning_details(review_id: int):
    s = get_session()
    try:
        review = s.query(HumanReviewCase).filter_by(review_id=review_id).first()
        if not review:
            raise HTTPException(404, "Review not found")
        if review.review_type != "DUNNING_REVIEW":
            raise HTTPException(400, "Not a dunning review")
        invoice = s.query(Invoice).filter_by(invoice_id=review.entity_id).first()
        if not invoice:
            raise HTTPException(404, "Invoice not found")
        po = s.query(PurchaseOrder).filter_by(po_id=invoice.po_id).first()
        customer = s.query(Customer).filter_by(customer_id=po.customer_id).first()
        history = s.query(DunningAction).filter_by(invoice_id=invoice.invoice_id).order_by(DunningAction.action_date.asc()).all()
        invoice_evidence = s.query(CaseEvidence).filter_by(entity_type="Invoice", entity_id=invoice.invoice_id).all()
        customer_evidence = s.query(CaseEvidence).filter_by(entity_type="Customer", entity_id=str(customer.customer_id)).all()
        return {
            "invoice": {"invoice_id": invoice.invoice_id, "amount": float(invoice.total_amount), "due_date": invoice.due_date, "days_overdue": max(0, (datetime.utcnow() - invoice.due_date).days), "status": invoice.status.value},
            "customer": {"customer_id": customer.customer_id, "company_name": customer.company_name},
            "history": [{"date": x.action_date, "type": x.action_type, "message": x.message, "status": x.status.value} for x in history],
            "evidence": [{"source": x.source, "source_system": x.source_system, "type": x.evidence_type, "content": x.content} for x in invoice_evidence + customer_evidence]
        }
    finally:
        s.close()

@app.get("/agent-actions")
def get_agent_actions():
    s = get_session()
    try:
        actions = s.query(AgentAction).order_by(AgentAction.created_at.desc()).all()
        return [{
            "action_id": x.action_id,
            "agent_name": x.agent_name,
            "entity_type": x.entity_type,
            "entity_id": x.entity_id,
            "action": x.action,
            "decision": x.decision,
            "reason": x.reason,
            "confidence": float(x.confidence) if x.confidence is not None else None,
            "status": x.status.value,
            "created_at": x.created_at
        } for x in actions]
    finally:
        s.close()

@app.get("/cases/{entity_id}")
def get_case_overview(entity_id: str):
    s = get_session()
    try:
        invoice_ids, payment_ids, po_ids, grn_ids, customer_ids = set(), set(), set(), set(), set()
        invoice = s.query(Invoice).filter_by(invoice_id=entity_id).first()
        payment = s.query(BankRemittance).filter_by(payment_id=entity_id).first()
        po = s.query(PurchaseOrder).filter_by(po_id=entity_id).first()

        if invoice:
            invoice_ids.add(invoice.invoice_id)
        if payment:
            payment_ids.add(payment.payment_id)
            apps = s.query(PaymentApplication).filter_by(payment_id=payment.payment_id).all()
            invoice_ids.update(x.invoice_id for x in apps)
            if payment.matched_invoice_id:
                invoice_ids.add(payment.matched_invoice_id)
            if not invoice_ids:
                invoice_ids.update(x.invoice_id for x in _candidate_invoices_for_payment(s, payment))
        if po:
            po_ids.add(po.po_id)
            invoice_ids.update(x.invoice_id for x in s.query(Invoice).filter_by(po_id=po.po_id).all())
        if not invoice and not payment and not po:
            raise HTTPException(404, "Case not found")

        for inv_id in list(invoice_ids):
            inv = s.query(Invoice).filter_by(invoice_id=inv_id).first()
            if inv:
                po_ids.add(inv.po_id)
                if inv.grn_id:
                    grn_ids.add(inv.grn_id)
        for po_id in list(po_ids):
            p = s.query(PurchaseOrder).filter_by(po_id=po_id).first()
            if p:
                customer_ids.add(p.customer_id)
        if invoice_ids:
            apps = s.query(PaymentApplication).filter(PaymentApplication.invoice_id.in_(invoice_ids)).all()
            payment_ids.update(x.payment_id for x in apps)
            direct = s.query(BankRemittance).filter(BankRemittance.matched_invoice_id.in_(invoice_ids)).all()
            payment_ids.update(x.payment_id for x in direct)

        related_ids = set(invoice_ids) | set(payment_ids) | set(po_ids) | set(grn_ids) | {str(x) for x in customer_ids}
        invoices = s.query(Invoice).filter(Invoice.invoice_id.in_(invoice_ids)).all() if invoice_ids else []
        payments = s.query(BankRemittance).filter(BankRemittance.payment_id.in_(payment_ids)).all() if payment_ids else []
        actions = s.query(AgentAction).filter(AgentAction.entity_id.in_(related_ids)).all() if related_ids else []
        reviews = s.query(HumanReviewCase).filter(HumanReviewCase.entity_id.in_(related_ids)).all() if related_ids else []
        dunning = s.query(DunningAction).filter(DunningAction.invoice_id.in_(invoice_ids)).all() if invoice_ids else []
        evidence = s.query(CaseEvidence).filter(CaseEvidence.entity_id.in_(related_ids)).all() if related_ids else []
        applications = s.query(PaymentApplication).filter(
            (PaymentApplication.invoice_id.in_(invoice_ids)) | (PaymentApplication.payment_id.in_(payment_ids))
        ).all() if invoice_ids or payment_ids else []
        customers = s.query(Customer).filter(Customer.customer_id.in_(customer_ids)).all() if customer_ids else []

        timeline = []
        for x in actions:
            timeline.append({"date": x.created_at, "type": "AGENT", "title": f"{x.agent_name}: {x.decision}", "detail": x.reason, "status": x.status.value})
        for x in reviews:
            timeline.append({"date": x.created_at, "type": "HUMAN REVIEW", "title": x.review_type.replace("_", " ").title(), "detail": x.reason, "status": x.status})
        for x in dunning:
            timeline.append({"date": x.action_date, "type": "DUNNING", "title": x.action_type.replace("_", " ").title(), "detail": x.message, "status": x.status.value})
        for x in evidence:
            timeline.append({"date": x.created_at, "type": "EVIDENCE", "title": x.evidence_type.replace("_", " ").title(), "detail": x.content, "status": x.source})
        for x in applications:
            timeline.append({"date": x.created_at, "type": "PAYMENT", "title": f"{x.payment_id} applied to {x.invoice_id}", "detail": f"£{float(x.matched_amount):,.2f} allocated to invoice {x.invoice_id}.", "status": x.status})
        timeline.sort(key=lambda x: x["date"] or datetime.min, reverse=True)

        total_invoice_value = sum(float(x.total_amount) for x in invoices)
        open_reviews = sum(1 for x in reviews if x.status == "OPEN")
        summary = (
            f"This case links {len(invoices)} invoice(s) worth £{total_invoice_value:,.2f}, "
            f"{len(payments)} payment(s), {len(actions)} agent decision(s) and {len(reviews)} human review record(s). "
            f"{open_reviews} review(s) currently require attention."
        )
        return {
            "entity_id": entity_id,
            "summary": summary,
            "stats": {"invoices": len(invoices), "invoice_value": total_invoice_value, "payments": len(payments), "agent_actions": len(actions), "open_reviews": open_reviews},
            "customers": [x.company_name for x in customers],
            "related": {"invoices": sorted(invoice_ids), "payments": sorted(payment_ids), "purchase_orders": sorted(po_ids), "grns": sorted(grn_ids)},
            "invoices": [{"invoice_id": x.invoice_id, "amount": float(x.total_amount), "status": x.status.value, "qa_status": x.qa_status.value, "due_date": x.due_date} for x in invoices],
            "payments": [{"payment_id": x.payment_id, "amount": float(x.amount_received), "status": x.status.value, "bank_text": x.raw_bank_text} for x in payments],
            "timeline": timeline
        }
    finally:
        s.close()
