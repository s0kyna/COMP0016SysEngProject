# mocks.py
from datetime import date
from o2c_protocols import Company, Ledger, O2CController
from models import (
    BankRemittance, GRNStatus, GeneralLedgerEntry, 
    GoodsReceivedNote, Invoice, PurchaseOrder, 
    PurchaseOrderStatus, RemittanceStatus
)

# ==========================================
# THE MOCK IMPLEMENTATIONS
# ==========================================

class MockO2CController(O2CController):
    """
    A simple list-based tracker for unit testing the sequence of events.
    """
    def __init__(self):
        self.events = []
    
    def on_receive_purchase_order(self, po: PurchaseOrder):
        self.events.append("po")
        
    def on_goods_sent(self, order_id: str):
        self.events.append("goods_sent")

    def on_receive_grn(self, grn: GoodsReceivedNote):
        self.events.append("grn")
        
    def on_send_invoice(self, invoice: Invoice):
        self.events.append("invoice")

    def on_receive_payments(self, payment: BankRemittance):
        self.events.append("payment")
        
    def on_record_payment(self, entry: GeneralLedgerEntry):
        self.events.append("ledger_entry")

    # --- Exception Tracking ---
    def on_follow_up_with_customer(self, issue: str):
        self.events.append("follow_up_customer")

    def on_follow_up_with_warehouse(self, issue: str):
        self.events.append("follow_up_warehouse")


class MockCompany(Company):
    """
    A concrete implementation of the Company Interface, now with Dependency Injection.
    """
    def __init__(self, event_tracker: O2CController):
        self.event_tracker = event_tracker

    def receive_purchase_order(self) -> PurchaseOrder:
        print("[MockCompany] Stage 1: Receiving Purchase Order...")
        po = PurchaseOrder(
            po_id="PO-1001",
            customer_id=101,
            order_date=date.today(),
            expected_total=25000.00,
            status=PurchaseOrderStatus.PENDING
        )
        print(f"  -> Received {po.po_id} for £{po.expected_total}")
        
        # Trigger the event tracker!
        self.event_tracker.on_receive_purchase_order(po)
        return po

    def acknowledge_goods_are_sent(self, order_id: str) -> None:
        print(f"\n[MockCompany] Stage 2: Warehouse is packing and shipping {order_id}...")
        print("  -> Goods have successfully left the warehouse.")
        
        # Trigger the event tracker!
        self.event_tracker.on_goods_sent(order_id)

    def receive_grn(self) -> GoodsReceivedNote:
        print("\n[MockCompany] Stage 2b: Receiving Goods Received Note (GRN)...")
        grn = GoodsReceivedNote(
            grn_id="GRN-5001",
            po_id="PO-1001",
            delivery_date=date.today(),
            received_by_signature="Warehouse Dave",
            status=GRNStatus.FULL_DELIVERY
        )
        print(f"  -> {grn.grn_id} logged. Status: {grn.status.name}")
        
        # Trigger the event tracker!
        self.event_tracker.on_receive_grn(grn)
        return grn

    def send_invoice(self, invoice: Invoice) -> None:
        print(f"\n[MockCompany] Stage 3: Sending Invoice {invoice.invoice_id} to customer...")
        print(f"  -> Billed for £{invoice.total_amount}. QA Status: {invoice.qa_status.name}")
        
        # Trigger the event tracker!
        self.event_tracker.on_send_invoice(invoice)

    def receive_payments(self) -> BankRemittance:
        print("\n[MockCompany] Stage 4: Checking Bank Feed for payments...")
        remittance = BankRemittance(
            payment_id="TXN-77881",
            payment_date=date.today(),
            amount_received=25000.00,
            raw_bank_text="WIRE ACME CORP REF INV-9901",
            status=RemittanceStatus.UNPROCESSED,
            matched_invoice_id=None
        )
        print(f"  -> Received £{remittance.amount_received} from bank.")
        
        # Trigger the event tracker!
        self.event_tracker.on_receive_payments(remittance)
        return remittance

    # --- Exception Handling Actions ---
    def follow_up_with_customer(self, message: str) -> None:
        print(f"\n[MockCompany] Exception: Generating email to Customer...")
        print(f"  -> Message: {message}")
        
        # Trigger the event tracker!
        self.event_tracker.on_follow_up_with_customer(message)

    def follow_up_with_warehouse(self, message: str) -> None:
        print(f"\n[MockCompany] Exception: Generating email to Warehouse...")
        print(f"  -> Message: {message}")
        
        # Trigger the event tracker!
        self.event_tracker.on_follow_up_with_warehouse(message)


class MockGeneralLedger(Ledger):
    def __init__(self, event_tracker: O2CController):
        self.event_tracker = event_tracker

    def record_payment(self, entry: GeneralLedgerEntry) -> None:
        print("\n[MockLedger] Stage 5: Recording Revenue in General Ledger...")
        print(f"  -> SUCCESS! £{entry.credit_amount} recorded for {entry.invoice_id}.")
        
        # Trigger the event tracker!
        self.event_tracker.on_record_payment(entry)