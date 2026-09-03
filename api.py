from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from db import get_session
from models import (
    HumanReviewCase, Invoice, BankRemittance, PaymentApplication,
    InvoiceStatus, InvoiceQAStatus, RemittanceStatus
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