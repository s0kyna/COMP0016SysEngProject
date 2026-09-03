# models.py
from enum import Enum
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, DateTime, Text,
    Enum as SQLEnum, ForeignKey, Numeric
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


# ==========================================
# STATUS ENUMS
# ==========================================

class PurchaseOrderStatus(Enum):
    PENDING = "PENDING"
    PARTIALLY_SHIPPED = "PARTIALLY_SHIPPED"
    FULFILLED = "FULFILLED"
    CLOSED = "CLOSED"


class OrderLineItemStatus(Enum):
    ALLOCATED = "ALLOCATED"
    BACKORDERED = "BACKORDERED"
    SHIPPED = "SHIPPED"
    MISMATCH_FLAGGED = "MISMATCH_FLAGGED"


class GRNStatus(Enum):
    FULL_DELIVERY = "FULL_DELIVERY"
    SHORT_SHIPPED = "SHORT_SHIPPED"
    DAMAGED_IN_TRANSIT = "DAMAGED_IN_TRANSIT"


class InvoiceQAStatus(Enum):
    PENDING = "PENDING"
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"


class InvoiceStatus(Enum):
    OUTSTANDING = "OUTSTANDING"
    PAID = "PAID"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    OVERDUE = "OVERDUE"
    DISPUTED = "DISPUTED"


class RemittanceStatus(Enum):
    UNPROCESSED = "UNPROCESSED"
    MATCHED_AUTO = "MATCHED_AUTO"
    MATCHED_MANUAL = "MATCHED_MANUAL"
    UNMATCHED_ESCALATED = "UNMATCHED_ESCALATED"


class DisputeStatus(Enum):
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    RESOLVED = "RESOLVED"
    ESCALATED = "ESCALATED"


class DunningActionStatus(Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    ESCALATED = "ESCALATED"


class AgentActionStatus(Enum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ESCALATED = "ESCALATED"
    HUMAN_REVIEW = "HUMAN_REVIEW"


# ==========================================
# CUSTOMER
# ==========================================

class Customer(Base):
    __tablename__ = "customers"

    customer_id = Column(Integer, primary_key=True, autoincrement=True)
    company_name = Column(String, nullable=False)
    billing_email = Column(String, nullable=False)
    contact_email = Column(String, nullable=False)
    credit_limit = Column(Numeric(12, 2, asdecimal=True), nullable=False)


# ==========================================
# PURCHASE ORDER
# ==========================================

class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    po_id = Column(String, primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.customer_id"), nullable=False)
    order_date = Column(DateTime, default=datetime.utcnow)
    expected_total = Column(Numeric(12, 2, asdecimal=True), nullable=False)
    status = Column(SQLEnum(PurchaseOrderStatus), nullable=False)


# ==========================================
# ORDER LINE ITEM
# ==========================================

class OrderLineItem(Base):
    __tablename__ = "order_line_items"

    line_id = Column(Integer, primary_key=True, autoincrement=True)
    po_id = Column(String, ForeignKey("purchase_orders.po_id"), nullable=False)
    item_desc = Column(String, nullable=False)
    unit_price = Column(Numeric(12, 2, asdecimal=True), nullable=False)
    ordered_qty = Column(Integer, nullable=False)
    received_qty = Column(Integer, default=0)
    billed_qty = Column(Integer, default=0)
    status = Column(SQLEnum(OrderLineItemStatus), nullable=False)


# ==========================================
# GOODS RECEIVED NOTE
# ==========================================

class GoodsReceivedNote(Base):
    __tablename__ = "goods_received_notes"

    grn_id = Column(String, primary_key=True)
    po_id = Column(String, ForeignKey("purchase_orders.po_id"), nullable=False)
    delivery_date = Column(DateTime, default=datetime.utcnow)
    received_by_signature = Column(String, nullable=False)
    status = Column(SQLEnum(GRNStatus), nullable=False)


# ==========================================
# INVOICE
# ==========================================

class Invoice(Base):
    __tablename__ = "invoices"

    invoice_id = Column(String, primary_key=True)
    po_id = Column(String, ForeignKey("purchase_orders.po_id"), nullable=False)
    grn_id = Column(String, ForeignKey("goods_received_notes.grn_id"), nullable=False)
    issue_date = Column(DateTime, default=datetime.utcnow)
    due_date = Column(DateTime, nullable=False)
    total_amount = Column(Numeric(12, 2, asdecimal=True), nullable=False)
    qa_status = Column(SQLEnum(InvoiceQAStatus), nullable=False)
    status = Column(SQLEnum(InvoiceStatus), nullable=False)


# ==========================================
# BANK REMITTANCE
# ==========================================

class BankRemittance(Base):
    __tablename__ = "bank_remittances"

    payment_id = Column(String, primary_key=True)
    payment_date = Column(DateTime, default=datetime.utcnow)
    amount_received = Column(Numeric(12, 2, asdecimal=True), nullable=False)
    raw_bank_text = Column(String, nullable=False)
    status = Column(SQLEnum(RemittanceStatus), nullable=False)
    matched_invoice_id = Column(
        String,
        ForeignKey("invoices.invoice_id"),
        nullable=True
    )


# ==========================================
# PAYMENT APPLICATION
# ==========================================

class PaymentApplication(Base):
    __tablename__ = "payment_applications"

    payment_application_id = Column(Integer, primary_key=True, autoincrement=True)
    payment_id = Column(
        String,
        ForeignKey("bank_remittances.payment_id"),
        nullable=False
    )
    invoice_id = Column(
        String,
        ForeignKey("invoices.invoice_id"),
        nullable=False
    )
    matched_amount = Column(Numeric(12, 2, asdecimal=True), nullable=False)
    match_confidence = Column(Numeric(5, 2), nullable=True)
    status = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


# ==========================================
# DISPUTES
# ==========================================

class Dispute(Base):
    __tablename__ = "disputes"

    dispute_id = Column(String, primary_key=True)
    invoice_id = Column(
        String,
        ForeignKey("invoices.invoice_id"),
        nullable=False
    )
    customer_id = Column(
        Integer,
        ForeignKey("customers.customer_id"),
        nullable=False
    )
    opened_date = Column(DateTime, default=datetime.utcnow)
    reason = Column(String, nullable=False)
    description = Column(String, nullable=False)
    status = Column(SQLEnum(DisputeStatus), nullable=False)
    resolution = Column(String, nullable=True)
    resolved_date = Column(DateTime, nullable=True)


# ==========================================
# GENERAL LEDGER
# ==========================================

class GeneralLedgerEntry(Base):
    __tablename__ = "general_ledger"

    entry_id = Column(String, primary_key=True)
    date_recorded = Column(DateTime, default=datetime.utcnow)
    account_name = Column(String, nullable=False)
    invoice_id = Column(
        String,
        ForeignKey("invoices.invoice_id"),
        nullable=False
    )
    credit_amount = Column(Numeric(12, 2, asdecimal=True), nullable=False)


# ==========================================
# DUNNING ACTIONS
# ==========================================

class DunningAction(Base):
    __tablename__ = "dunning_actions"

    dunning_id = Column(Integer, primary_key=True, autoincrement=True)
    invoice_id = Column(
        String,
        ForeignKey("invoices.invoice_id"),
        nullable=False
    )
    customer_id = Column(
        Integer,
        ForeignKey("customers.customer_id"),
        nullable=False
    )
    action_date = Column(DateTime, default=datetime.utcnow)
    action_type = Column(String, nullable=False)
    message = Column(String, nullable=False)
    status = Column(SQLEnum(DunningActionStatus), nullable=False)


# ==========================================
# AI AGENT ACTIONS / AUDIT LOG
# ==========================================

class AgentAction(Base):
    __tablename__ = "agent_actions"

    action_id = Column(Integer, primary_key=True, autoincrement=True)
    agent_name = Column(String, nullable=False)
    entity_type = Column(String, nullable=False)
    entity_id = Column(String, nullable=False)
    action = Column(String, nullable=False)
    decision = Column(String, nullable=True)
    reason = Column(String, nullable=True)
    confidence = Column(Numeric(5, 2), nullable=True)
    status = Column(SQLEnum(AgentActionStatus), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class CaseEvidence(Base):
    __tablename__ = "case_evidence"

    evidence_id = Column(Integer, primary_key=True, autoincrement=True)
    entity_type = Column(String, nullable=False)
    entity_id = Column(String, nullable=False)
    
    source_system = Column(String, nullable=False) # ERP, EMAIL, WAREHOUSE_SYSTEM, CRM, etc.
    source = Column(String, nullable=False)        # Finance, Warehouse, Customer, Supplier...
    evidence_type = Column(String, nullable=False) # NOTE, EMAIL, APPROVAL, ATTACHMENT, DELIVERY_COMMENT
    content = Column(Text, nullable=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)

class HumanReviewCase(Base):
    __tablename__ = "human_review_cases"

    review_id = Column(Integer, primary_key=True, autoincrement=True)
    review_type = Column(String, nullable=False)
    entity_type = Column(String, nullable=False)
    entity_id = Column(String, nullable=False)
    reason = Column(Text, nullable=False)
    recommended_action = Column(Text)
    status = Column(String, default="OPEN")
    created_at = Column(DateTime, default=datetime.utcnow)