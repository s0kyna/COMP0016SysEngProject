from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from db import get_session
from datetime import datetime
from models import (
    HumanReviewCase, Invoice, BankRemittance, PaymentApplication,
    InvoiceStatus, InvoiceQAStatus, RemittanceStatus, PurchaseOrder,
    GoodsReceivedNote, OrderLineItem, CaseEvidence, AgentAction, 
    Customer, DunningAction
)

app = FastAPI(title="O2C Agents API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

class ReviewAction(BaseModel):
    action: str
    invoice_id: str | None = None
    note: str | None = None

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

            if action == "MATCH":
                if not data.invoice_id:
                    raise HTTPException(400, "invoice_id required")

                invoice = s.query(Invoice).filter_by(invoice_id=data.invoice_id).first()
                if not invoice:
                    raise HTTPException(404, "Invoice not found")

                s.add(PaymentApplication(
                    payment_id=payment.payment_id,
                    invoice_id=invoice.invoice_id,
                    matched_amount=payment.amount_received,
                    match_confidence=None,
                    status="MATCHED_MANUAL"
                ))

                payment.matched_invoice_id = invoice.invoice_id
                payment.status = RemittanceStatus.MATCHED_MANUAL
                invoice.status = InvoiceStatus.PAID
                review.status = "MATCHED"

            elif action == "LEAVE_UNMATCHED":
                review.status = "UNMATCHED"
            else:
                raise HTTPException(400, "Use MATCH or LEAVE_UNMATCHED")

        elif review.review_type == "DUNNING_REVIEW":
            if action not in {"SEND_REMINDER", "WAIT", "ESCALATE"}:
                raise HTTPException(400, "Use SEND_REMINDER, WAIT or ESCALATE")
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

        invoices = s.query(Invoice).filter(
            Invoice.status.in_([InvoiceStatus.OUTSTANDING, InvoiceStatus.PARTIALLY_PAID])
        ).all()

        return {
            "payment": {
                "payment_id": payment.payment_id,
                "amount": float(payment.amount_received),
                "raw_text": payment.raw_bank_text
            },
            "candidates": [{
                "invoice_id": i.invoice_id,
                "amount": float(i.total_amount),
                "status": i.status.value
            } for i in invoices]
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
            ("Invoice", invoice.invoice_id),
            ("PurchaseOrder", po.po_id),
            ("GRN", grn.grn_id),
            ("Customer", str(po.customer_id))
        ]

        evidence = []
        for entity_type, entity_id in entity_pairs:
            evidence += s.query(CaseEvidence).filter_by(
                entity_type=entity_type,
                entity_id=entity_id
            ).all()

        return {
            "invoice": {
                "invoice_id": invoice.invoice_id,
                "total_amount": float(invoice.total_amount),
                "status": invoice.status.value,
                "qa_status": invoice.qa_status.value
            },
            "purchase_order": {
                "po_id": po.po_id,
                "expected_total": float(po.expected_total),
                "status": po.status.value
            },
            "grn": {
                "grn_id": grn.grn_id,
                "status": grn.status.value
            },
            "lines": [{
                "line_id": x.line_id,
                "description": x.item_desc,
                "unit_price": float(x.unit_price),
                "ordered": x.ordered_qty,
                "received": x.received_qty,
                "billed": x.billed_qty
            } for x in lines],
            "evidence": [{
                "source_system": x.source_system,
                "source": x.source,
                "type": x.evidence_type,
                "content": x.content
            } for x in evidence]
        }
    finally:
        s.close()

@app.get("/agent-actions")
def get_agent_actions():
    s = get_session()
    try:
        actions = s.query(AgentAction).order_by(
            AgentAction.created_at.desc()
        ).all()

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
        actions = s.query(AgentAction).filter_by(
            entity_id=entity_id
        ).order_by(AgentAction.created_at.asc()).all()

        reviews = s.query(HumanReviewCase).filter_by(
            entity_id=entity_id
        ).order_by(HumanReviewCase.created_at.asc()).all()

        if not actions and not reviews:
            raise HTTPException(404, "Case not found")

        summary_parts = []

        for x in actions:
            summary_parts.append(
                f"{x.agent_name}: {x.decision}. {x.reason}"
            )

        for x in reviews:
            summary_parts.append(
                f"Human review {x.review_type}: {x.status}. {x.reason}"
            )

        return {
            "entity_id": entity_id,
            "summary": " ".join(summary_parts),
            "agent_actions": [{
                "action_id": x.action_id,
                "agent_name": x.agent_name,
                "decision": x.decision,
                "reason": x.reason,
                "status": x.status.value,
                "created_at": x.created_at
            } for x in actions],
            "reviews": [{
                "review_id": x.review_id,
                "review_type": x.review_type,
                "reason": x.reason,
                "recommended_action": x.recommended_action,
                "status": x.status,
                "created_at": x.created_at
            } for x in reviews]
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

        history = s.query(DunningAction).filter_by(
            invoice_id=invoice.invoice_id
        ).order_by(DunningAction.action_date.asc()).all()

        invoice_evidence = s.query(CaseEvidence).filter_by(
            entity_type="Invoice",
            entity_id=invoice.invoice_id
        ).all()

        customer_evidence = s.query(CaseEvidence).filter_by(
            entity_type="Customer",
            entity_id=str(customer.customer_id)
        ).all()

        days_overdue = max(
            0,
            (datetime.utcnow() - invoice.due_date).days
        )

        return {
            "invoice": {
                "invoice_id": invoice.invoice_id,
                "amount": float(invoice.total_amount),
                "due_date": invoice.due_date,
                "days_overdue": days_overdue,
                "status": invoice.status.value
            },
            "customer": {
                "customer_id": customer.customer_id,
                "company_name": customer.company_name
            },
            "history": [{
                "date": x.action_date,
                "type": x.action_type,
                "message": x.message,
                "status": x.status.value
            } for x in history],
            "evidence": [{
                "source": x.source,
                "source_system": x.source_system,
                "type": x.evidence_type,
                "content": x.content
            } for x in invoice_evidence + customer_evidence]
        }
    finally:
        s.close()