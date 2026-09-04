from datetime import datetime
from itertools import combinations
from collections import defaultdict

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
    apps = s.query(PaymentApplication).filter_by(invoice_id=invoice.invoice_id).all()
    applied = sum(float(x.matched_amount) for x in apps)
    return applied, max(0, float(invoice.total_amount) - applied)

def _payment_customer_ids(s, payment):
    text = (payment.raw_bank_text or "").lower()
    return [
        c.customer_id for c in s.query(Customer).all()
        if c.company_name and c.company_name.lower() in text
    ]

def _candidate_invoices_for_payment(s, payment):
    invoices = s.query(Invoice).filter(
        Invoice.status.in_([InvoiceStatus.OUTSTANDING, InvoiceStatus.PARTIALLY_PAID])
    ).all()

    customer_ids = _payment_customer_ids(s, payment)
    if customer_ids:
        po_ids = {
            x.po_id for x in s.query(PurchaseOrder).filter(
                PurchaseOrder.customer_id.in_(customer_ids)
            ).all()
        }
        invoices = [x for x in invoices if x.po_id in po_ids]

    amount = float(payment.amount_received)
    exact = [x for x in invoices if abs(_invoice_balance(s, x)[1] - amount) <= 0.01]
    if exact:
        return exact

    combo_ids = set()
    for size in range(2, min(3, len(invoices)) + 1):
        for combo in combinations(invoices, size):
            total = sum(_invoice_balance(s, x)[1] for x in combo)
            if abs(total - amount) <= 0.01:
                combo_ids.update(x.invoice_id for x in combo)

    if combo_ids:
        return [x for x in invoices if x.invoice_id in combo_ids]

    return sorted(
        invoices,
        key=lambda x: abs(_invoice_balance(s, x)[1] - amount)
    )[:5]

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
                    raise HTTPException(
                        400,
                        f"Allocated £{total_allocated:.2f}, but payment is £{float(payment.amount_received):.2f}"
                    )

                used = set()
                for allocation in data.allocations:
                    if allocation.invoice_id in used:
                        raise HTTPException(400, "Duplicate invoice allocation")
                    used.add(allocation.invoice_id)

                    invoice = s.query(Invoice).filter_by(
                        invoice_id=allocation.invoice_id
                    ).first()
                    if not invoice:
                        raise HTTPException(404, f"Invoice {allocation.invoice_id} not found")

                    already_paid, remaining = _invoice_balance(s, invoice)
                    if allocation.amount <= 0:
                        raise HTTPException(400, "Allocation must be greater than zero")
                    if allocation.amount > remaining + 0.01:
                        raise HTTPException(
                            400,
                            f"Allocation exceeds remaining balance for {invoice.invoice_id}"
                        )

                    s.add(PaymentApplication(
                        payment_id=payment.payment_id,
                        invoice_id=invoice.invoice_id,
                        matched_amount=allocation.amount,
                        match_confidence=None,
                        status="MATCHED_MANUAL"
                    ))

                    new_paid = already_paid + allocation.amount
                    invoice.status = (
                        InvoiceStatus.PAID
                        if new_paid >= float(invoice.total_amount) - 0.01
                        else InvoiceStatus.PARTIALLY_PAID
                    )

                payment.status = RemittanceStatus.MATCHED_MANUAL
                payment.matched_invoice_id = (
                    data.allocations[0].invoice_id
                    if len(data.allocations) == 1 else None
                )
                review.status = "MATCHED"

            elif action == "LEAVE_UNMATCHED":
                review.status = "UNMATCHED"
            else:
                raise HTTPException(400, "Use MATCH or LEAVE_UNMATCHED")

        elif review.review_type == "DUNNING_REVIEW":
            if action not in {"SEND_REMINDER", "WAIT", "ESCALATE"}:
                raise HTTPException(400, "Use SEND_REMINDER, WAIT or ESCALATE")

            invoice = s.query(Invoice).filter_by(invoice_id=review.entity_id).first()
            if not invoice:
                raise HTTPException(404, "Invoice not found")

            po = s.query(PurchaseOrder).filter_by(po_id=invoice.po_id).first()
            if not po:
                raise HTTPException(404, "Purchase order not found")

            if action == "SEND_REMINDER":
                dunning_type = "REMINDER"
                message = data.note or "Payment reminder approved by human reviewer."
                status = DunningActionStatus.SENT
            elif action == "WAIT":
                dunning_type = "WAIT"
                message = data.note or "Human reviewer paused further collection activity."
                status = DunningActionStatus.PENDING
            else:
                dunning_type = "ESCALATION"
                message = data.note or "Human reviewer escalated the case to senior collections."
                status = DunningActionStatus.ESCALATED

            s.add(DunningAction(
                invoice_id=invoice.invoice_id,
                customer_id=po.customer_id,
                action_date=datetime.utcnow(),
                action_type=dunning_type,
                message=message,
                status=status
            ))
            review.status = action

        else:
            raise HTTPException(400, "Unknown review type")

        review.resolved_at = datetime.utcnow()
        review.resolution_action = action
        review.resolution_note = data.note

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

        pairs = [
            ("Invoice", invoice.invoice_id),
            ("PurchaseOrder", po.po_id),
            ("GRN", grn.grn_id),
            ("Customer", str(po.customer_id))
        ]

        evidence = []
        for entity_type, entity_id in pairs:
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

        return {
            "invoice": {
                "invoice_id": invoice.invoice_id,
                "amount": float(invoice.total_amount),
                "due_date": invoice.due_date,
                "days_overdue": max(0, (datetime.utcnow() - invoice.due_date).days),
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

@app.get("/recent-cases")
def get_recent_cases():
    s = get_session()
    try:
        latest = {}

        def add(entity_id, summary, status, updated_at):
            if not entity_id or not updated_at:
                return
            current = latest.get(entity_id)
            if current is None or updated_at > current["updated_at"]:
                latest[entity_id] = {
                    "entity_id": entity_id,
                    "summary": summary,
                    "status": status,
                    "updated_at": updated_at
                }

        for x in s.query(AgentAction).all():
            add(
                x.entity_id,
                f"{x.agent_name}: {x.decision.replace('_', ' ')}",
                x.status.value,
                x.created_at
            )

        for x in s.query(HumanReviewCase).all():
            if x.resolved_at:
                add(
                    x.entity_id,
                    f"Human decision: {(x.resolution_action or x.status).replace('_', ' ').title()}",
                    x.status,
                    x.resolved_at
                )
            else:
                add(
                    x.entity_id,
                    x.review_type.replace("_", " ").title(),
                    x.status,
                    x.created_at
                )

        for x in s.query(DunningAction).all():
            add(
                x.invoice_id,
                f"Collections: {x.action_type.replace('_', ' ').title()}",
                x.status.value,
                x.action_date
            )

        for x in s.query(PaymentApplication).all():
            add(
                x.payment_id,
                f"Payment allocation updated",
                x.status,
                x.created_at
            )

        return sorted(
            latest.values(),
            key=lambda x: x["updated_at"],
            reverse=True
        )[:12]
    finally:
        s.close()

def _case_summary(entity_id, invoices, payments, actions, reviews, applications, dunning):
    customer_phrase = ""
    if invoices:
        statuses = sorted({x.status.value for x in invoices})
        customer_phrase = f" Invoice status: {', '.join(statuses)}."

    if payments:
        p = next((x for x in payments if x.payment_id == entity_id), payments[0])
        linked = [x for x in applications if x.payment_id == p.payment_id]
        if linked:
            alloc_text = ", ".join(
                f"£{float(x.matched_amount):,.2f} to {x.invoice_id}"
                for x in linked
            )
            return (
                f"Payment {p.payment_id} for £{float(p.amount_received):,.2f} is "
                f"{p.status.value.replace('_', ' ').lower()}. "
                f"It is allocated as {alloc_text}.{customer_phrase} "
                f"The case contains {len(actions)} agent decision(s) and "
                f"{sum(1 for x in reviews if x.status == 'OPEN')} open review(s)."
            )

    if invoices:
        total = sum(float(x.total_amount) for x in invoices)
        return (
            f"This case covers {len(invoices)} invoice(s) worth £{total:,.2f}."
            f"{customer_phrase} It contains {len(actions)} agent decision(s), "
            f"{len(dunning)} collection action(s), and "
            f"{sum(1 for x in reviews if x.status == 'OPEN')} open review(s)."
        )

    return (
        f"This case contains {len(actions)} agent decision(s) and "
        f"{len(reviews)} human review record(s)."
    )

@app.get("/cases/{entity_id}")
def get_case_overview(entity_id: str):
    s = get_session()
    try:
        invoice_ids, payment_ids, po_ids, grn_ids, customer_ids = (
            set(), set(), set(), set(), set()
        )

        invoice = s.query(Invoice).filter_by(invoice_id=entity_id).first()
        payment = s.query(BankRemittance).filter_by(payment_id=entity_id).first()
        po = s.query(PurchaseOrder).filter_by(po_id=entity_id).first()

        if invoice:
            invoice_ids.add(invoice.invoice_id)

        if payment:
            payment_ids.add(payment.payment_id)
            apps = s.query(PaymentApplication).filter_by(
                payment_id=payment.payment_id
            ).all()
            invoice_ids.update(x.invoice_id for x in apps)

            if payment.matched_invoice_id:
                invoice_ids.add(payment.matched_invoice_id)

            # IMPORTANT: unresolved candidate invoices are suggestions, not
            # confirmed case relationships. Do not merge them into Case Overview.

        if po:
            po_ids.add(po.po_id)
            invoice_ids.update(
                x.invoice_id for x in s.query(Invoice).filter_by(po_id=po.po_id).all()
            )

        if not invoice and not payment and not po:
            raise HTTPException(404, "Case not found")

        for inv_id in list(invoice_ids):
            inv = s.query(Invoice).filter_by(invoice_id=inv_id).first()
            if inv:
                po_ids.add(inv.po_id)
                if inv.grn_id:
                    grn_ids.add(inv.grn_id)

        for po_id in list(po_ids):
            related_po = s.query(PurchaseOrder).filter_by(po_id=po_id).first()
            if related_po:
                customer_ids.add(related_po.customer_id)

        if invoice_ids:
            apps = s.query(PaymentApplication).filter(
                PaymentApplication.invoice_id.in_(invoice_ids)
            ).all()
            payment_ids.update(x.payment_id for x in apps)

            direct = s.query(BankRemittance).filter(
                BankRemittance.matched_invoice_id.in_(invoice_ids)
            ).all()
            payment_ids.update(x.payment_id for x in direct)

        transaction_ids = (
            set(invoice_ids)
            | set(payment_ids)
            | set(po_ids)
            | set(grn_ids)
        )
        evidence_ids = transaction_ids | {str(x) for x in customer_ids}

        invoices = (
            s.query(Invoice).filter(Invoice.invoice_id.in_(invoice_ids)).all()
            if invoice_ids else []
        )
        payments = (
            s.query(BankRemittance).filter(
                BankRemittance.payment_id.in_(payment_ids)
            ).all()
            if payment_ids else []
        )
        actions = (
            s.query(AgentAction).filter(
                AgentAction.entity_id.in_(transaction_ids)
            ).all()
            if transaction_ids else []
        )
        reviews = (
            s.query(HumanReviewCase).filter(
                HumanReviewCase.entity_id.in_(transaction_ids)
            ).all()
            if transaction_ids else []
        )
        dunning = (
            s.query(DunningAction).filter(
                DunningAction.invoice_id.in_(invoice_ids)
            ).all()
            if invoice_ids else []
        )
        evidence = (
            s.query(CaseEvidence).filter(
                CaseEvidence.entity_id.in_(evidence_ids)
            ).all()
            if evidence_ids else []
        )
        applications = (
            s.query(PaymentApplication).filter(
                (PaymentApplication.invoice_id.in_(invoice_ids))
                | (PaymentApplication.payment_id.in_(payment_ids))
            ).all()
            if invoice_ids or payment_ids else []
        )
        customers = (
            s.query(Customer).filter(
                Customer.customer_id.in_(customer_ids)
            ).all()
            if customer_ids else []
        )

        timeline = []

        for x in actions:
            timeline.append({
                "date": x.created_at,
                "type": "AGENT",
                "title": f"{x.agent_name}: {x.decision.replace('_', ' ')}",
                "detail": x.reason,
                "status": x.status.value
            })

        for x in reviews:
            timeline.append({
                "date": x.created_at,
                "type": "HUMAN REVIEW",
                "title": f"{x.review_type.replace('_', ' ').title()} opened",
                "detail": x.reason,
                "status": "OPEN"
            })

            if x.resolved_at:
                resolution = x.resolution_action or x.status
                timeline.append({
                    "date": x.resolved_at,
                    "type": "HUMAN ACTION",
                    "title": resolution.replace("_", " ").title(),
                    "detail": (
                        x.resolution_note
                        or f"Human reviewer selected {resolution.replace('_', ' ').lower()}."
                    ),
                    "status": x.status
                })

        for x in dunning:
            timeline.append({
                "date": x.action_date,
                "type": "COLLECTIONS",
                "title": x.action_type.replace("_", " ").title(),
                "detail": x.message,
                "status": x.status.value
            })

        for x in evidence:
            timeline.append({
                "date": x.created_at,
                "type": "EVIDENCE",
                "title": x.evidence_type.replace("_", " ").title(),
                "detail": x.content,
                "status": x.source
            })

        apps_by_payment = defaultdict(list)
        for x in applications:
            apps_by_payment[x.payment_id].append(x)

        for payment_id, apps in apps_by_payment.items():
            total = sum(float(x.matched_amount) for x in apps)
            if len(apps) == 1:
                title = f"Payment applied to {apps[0].invoice_id}"
                detail = f"£{total:,.2f} allocated to {apps[0].invoice_id}."
            else:
                title = f"{payment_id} split across {len(apps)} invoices"
                detail = "; ".join(
                    f"£{float(x.matched_amount):,.2f} → {x.invoice_id}"
                    for x in apps
                )
            timeline.append({
                "date": max(x.created_at for x in apps),
                "type": "PAYMENT",
                "title": title,
                "detail": detail,
                "status": apps[0].status
            })

        timeline.sort(
            key=lambda x: x["date"] or datetime.min,
            reverse=True
        )

        total_invoice_value = sum(float(x.total_amount) for x in invoices)
        open_reviews = sum(1 for x in reviews if x.status == "OPEN")

        summary = _case_summary(
            entity_id, invoices, payments, actions,
            reviews, applications, dunning
        )

        return {
            "entity_id": entity_id,
            "summary": summary,
            "stats": {
                "invoices": len(invoices),
                "invoice_value": total_invoice_value,
                "payments": len(payments),
                "agent_actions": len(actions),
                "open_reviews": open_reviews
            },
            "customers": [x.company_name for x in customers],
            "related": {
                "invoices": sorted(invoice_ids),
                "payments": sorted(payment_ids),
                "purchase_orders": sorted(po_ids),
                "grns": sorted(grn_ids)
            },
            "invoices": [{
                "invoice_id": x.invoice_id,
                "amount": float(x.total_amount),
                "status": x.status.value,
                "qa_status": x.qa_status.value,
                "due_date": x.due_date
            } for x in invoices],
            "payments": [{
                "payment_id": x.payment_id,
                "amount": float(x.amount_received),
                "status": x.status.value,
                "bank_text": x.raw_bank_text
            } for x in payments],
            "allocations": [{
                "payment_id": x.payment_id,
                "invoice_id": x.invoice_id,
                "amount": float(x.matched_amount),
                "status": x.status,
                "created_at": x.created_at
            } for x in applications],
            "timeline": timeline
        }
    finally:
        s.close()
