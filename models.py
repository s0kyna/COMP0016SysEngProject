from dataclasses import dataclass
from enum import Enum
from datetime import date
from typing import Optional

# ==========================================
# STATUS ENUMS
# ==========================================

class PurchaseOrderStatus(Enum):
    """
    Tracks the macro-level progress of the entire order.
    
    Attrs:
        PENDING: The order is waiting to be processed/shipped.
        PARTIALLY_SHIPPED: Some items have shipped, waiting on the rest.
        FULFILLED: All items have been shipped by the warehouse.
        CLOSED: All items have been received by the buyer and confirmed/paid.
    """
    PENDING = 0
    PARTIALLY_SHIPPED = 1
    FULFILLED = 2
    CLOSED = 3


class OrderLineItemStatus(Enum):
    """
    Tracks the micro-level status of a specific product to handle edge cases.
    
    Attrs:
        ALLOCATED: Sitting in the warehouse ready to go.
        BACKORDERED: Out of stock, delaying this specific item.
        SHIPPED: Successfully left the warehouse.
        MISMATCH_FLAGGED: The AI QA Agent found a discrepancy with this item.
    """
    ALLOCATED = 0
    BACKORDERED = 1
    SHIPPED = 2
    MISMATCH_FLAGGED = 3


class GRNStatus(Enum):
    """
    Tracks the physical reality of what arrived at the receiving dock.
    
    Attrs:
        FULL_DELIVERY: Everything requested on the PO arrived safely.
        SHORT_SHIPPED: Fewer items arrived than were ordered.
        DAMAGED_IN_TRANSIT: Items arrived but are broken/unusable.
    """
    FULL_DELIVERY = 0
    SHORT_SHIPPED = 1
    DAMAGED_IN_TRANSIT = 2


class InvoiceQAStatus(Enum):
    """
    Tracks the outcome of the AI-driven 3-Way Match.
    
    Attrs:
        PENDING: The invoice has not been checked yet.
        MATCH: PO, GRN, and Invoice align perfectly. Approved for payment.
        MISMATCH: Discrepancy found (price, quantity, or description).
    """
    PENDING = 0
    MATCH = 1
    MISMATCH = 2

class RemittanceStatus(Enum):
    """
    Tracks whether a bank payment has been matched to an invoice.
    
    Attrs:
        UNPROCESSED: Just arrived from the bank feed. The AI hasn't looked at it yet.
        MATCHED_AUTO: The AI CashApp Agent successfully linked it to an invoice.
        MATCHED_MANUAL: A human manager had to intervene and link it manually (HITL).
        UNMATCHED_ESCALATED: The AI is confused and escalated it to a human.
    """
    UNPROCESSED = 0
    MATCHED_AUTO = 1
    MATCHED_MANUAL = 2
    UNMATCHED_ESCALATED = 3

# ==========================================
# DATACLASS MODELS (TABLES)
# ==========================================

@dataclass
class Customer:
    """
    The source of truth for buyers. Used by agents to know who to contact and trust.
    
    Attrs:
        customer_id: The unique identifier for the buyer.
        company_name: The legal name of the buyer's company (e.g., 'Acme Corp').
        billing_email: Used by the Dunning Agent to send late payment reminders.
        contact_email: Used by the Dispute Triage Agent to send resolution emails.
        credit_limit: Checked by the Supervisor Agent before approving large new orders.
    """
    customer_id: int
    company_name: str
    billing_email: str
    contact_email: str
    credit_limit: float


@dataclass
class PurchaseOrder:
    """
    The overall request from the buyer (The Header).

    Attrs:
        po_id: The unique tracking ID for the order (e.g., 'PO-1001').
        customer_id: Links to the Customer table.
        order_date: The date the purchase order was formally created.
        expected_total: What the customer expects to pay for the whole order.
        status: The macro-level state of the order (PurchaseOrderStatus).
    """
    po_id: str
    customer_id: int
    order_date: date
    expected_total: float
    status: PurchaseOrderStatus


@dataclass
class OrderLineItem:
    """
    The specific items requested (The Detail). 
    This is the critical bridge table where the AI Agent performs the 3-Way Match.

    Attrs:
        line_id: A unique ID for this specific row/item in the database.
        po_id: Links back to the PurchaseOrder header.
        item_desc: What the product is (e.g., 'Industrial Widget V2').
        unit_price: The agreed-upon price for a single unit.
        ordered_qty: How many units were requested (Document 1: The PO).
        received_qty: How many units actually arrived (Document 2: The GRN).
        billed_qty: How many units the company charged for (Document 3: The Invoice).
        status: The micro-level state of this specific item (OrderLineItemStatus).
    """
    line_id: int
    po_id: str
    item_desc: str
    unit_price: float
    ordered_qty: int
    received_qty: int
    billed_qty: int
    status: OrderLineItemStatus


@dataclass
class GoodsReceivedNote:
    """
    The physical delivery receipt from the warehouse confirming what actually happened.

    Attrs:
        grn_id: The unique tracking ID for the shipment.
        po_id: Links to the PurchaseOrder to prove which order this fulfills.
        delivery_date: When the physical goods arrived.
        received_by_signature: The name of the warehouse worker who signed for it.
        status: The physical state of the delivery (GRNStatus).
    """
    grn_id: str
    po_id: str
    delivery_date: date
    received_by_signature: str
    status: GRNStatus


@dataclass
class Invoice:
    """
    The final financial demand sent to the buyer.

    Attrs:
        invoice_id: The unique tracking ID for the bill.
        po_id: Links to the PurchaseOrder to justify the bill.
        grn_id: Links to the GRN to prove the delivery actually happened.
        issue_date: When the bill was sent.
        total_amount: The final amount of money requested.
        qa_status: The result of the AI's 3-Way Match validation (InvoiceQAStatus).
    """
    invoice_id: str
    po_id: str
    grn_id: str
    issue_date: date
    total_amount: float
    qa_status: InvoiceQAStatus


@dataclass
class BankRemittance:
    """
    The messy reality of bank transfers. Used by the CashApp Agent to close the O2C loop.
    
    Attrs:
        payment_id: The unique transaction ID from the bank (e.g., 'TXN-001').
        payment_date: When the money actually hit the company's bank account.
        amount_received: The exact monetary value received.
        raw_bank_text: The unstructured, messy text attached to the bank transfer.
                       (The AI uses this to perform fuzzy matching).
        matched_invoice_id: Links to the Invoice table. Starts as None!
        status: The processing state of the payment (RemittanceStatus).
    """
    payment_id: str
    payment_date: date
    amount_received: float
    raw_bank_text: str
    status: RemittanceStatus
    matched_invoice_id: Optional[str] = None  # Crucial: Starts empty!

@dataclass
class GeneralLedgerEntry:
    """
    The official accounting book. Once a record is written here, revenue is officially recognized.
    
    Attrs:
        entry_id: Unique ID for the ledger row (e.g., 'GL-2026-001').
        date_recorded: When the revenue was recognized.
        account_name: Where the money goes (e.g., 'Software Sales Revenue').
        invoice_id: The invoice this revenue came from.
        credit_amount: The money added to the company's revenue.
    """
    entry_id: str
    date_recorded: date
    account_name: str
    invoice_id: str
    credit_amount: float