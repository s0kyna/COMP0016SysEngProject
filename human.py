## human.py
from models import Invoice, PurchaseOrder, GoodsReceivedNote

class ComplaintLetter:
    def __init__(self, message: str):
        self.message = message

class Human:
    """Represents the physical human doing manual cognitive work."""
    
    def get_invoice(self, grn: GoodsReceivedNote) -> Invoice:
        print("  🧑‍💻 [Human] Manually drafting an invoice based on the GRN...")
        from datetime import date
        from models import InvoiceQAStatus
        # Human generates a draft based on what they see
        return Invoice("INV-9901", grn.po_id, grn.grn_id, date.today(), 25000.00, InvoiceQAStatus.PENDING)
    
    def is_matching(self, po: PurchaseOrder, grn: GoodsReceivedNote, invoice: Invoice) -> bool:
        print("  🧑‍💻 [Human] Staring at monitors, comparing PO, GRN, and Invoice...")
        # A simple check: do the expected totals and PO IDs match?
        return po.expected_total == invoice.total_amount and po.po_id == grn.po_id
    
    def complain(self, issue: str) -> ComplaintLetter:
        print(f"  😡 [Human] GRRRRR! Discrepancy found! Typing complaint about: {issue}")
        return ComplaintLetter(f"Fix this issue immediately: {issue}")