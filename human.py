from datetime import datetime, timedelta

from models import (
    Invoice,
    PurchaseOrder,
    GoodsReceivedNote,
    InvoiceQAStatus,
    InvoiceStatus,
)


class ComplaintLetter:
    def __init__(self, message: str):
        self.message = message


class Human:
    """Represents the human performing manual O2C cognitive work."""

    def get_invoice(self, grn: GoodsReceivedNote) -> Invoice:
        print("  🧑‍💻 [Human] Manually drafting an invoice based on the GRN...")

        return Invoice(
            invoice_id="INV-9901",
            po_id=grn.po_id,
            grn_id=grn.grn_id,
            issue_date=datetime.utcnow(),
            due_date=datetime.utcnow() + timedelta(days=30),
            total_amount=25000.00,
            qa_status=InvoiceQAStatus.PENDING,
            status=InvoiceStatus.OUTSTANDING,
        )

    def is_matching(self, po, grn, invoice):
        print(
            "  🧑‍💻 [Human] Staring at monitors, "
            "comparing PO, GRN, and Invoice..."
        )

        return (
            po.expected_total == invoice.total_amount
            and po.po_id == grn.po_id
        )

    def complain(self, issue):
        print(
            f"  😡 [Human] GRRRRR! Discrepancy found! "
            f"Typing complaint about: {issue}"
        )

        return ComplaintLetter(
            f"Fix this issue immediately: {issue}"
        )