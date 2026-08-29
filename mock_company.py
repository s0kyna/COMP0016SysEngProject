from datetime import date
from deterministic_o2c import CompanyInterface, LedgerInterface
from models import BankRemittance, GRNStatus, GeneralLedgerEntry, GoodsReceivedNote, Invoice, PurchaseOrder, PurchaseOrderStatus, RemittanceStatus


class MockCompany(CompanyInterface):
    """
    A concrete implementation of the CompanyInterface.
    Python will crash if this class fails to include all the @abstractmethods above!
    """
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
        return po

    def acknowledge_goods_are_sent(self, order_id: str) -> None:
        print(f"\n[MockCompany] Stage 2: Warehouse is packing and shipping {order_id}...")
        print("  -> Goods have successfully left the warehouse.")

    def recieve_grn(self) -> GoodsReceivedNote:
        print("\n[MockCompany] Stage 2b: Receiving Goods Received Note (GRN)...")
        grn = GoodsReceivedNote(
            grn_id="GRN-5001",
            po_id="PO-1001",
            delivery_date=date.today(),
            received_by_signature="Warehouse Dave",
            status=GRNStatus.FULL_DELIVERY
        )
        print(f"  -> {grn.grn_id} logged. Status: {grn.status.name}")
        return grn

    def send_invoice(self, invoice: Invoice) -> None:
        print(f"\n[MockCompany] Stage 3: Sending Invoice {invoice.invoice_id} to customer...")
        print(f"  -> Billed for £{invoice.total_amount}. QA Status: {invoice.qa_status.name}")

    def recieve_payments(self) -> BankRemittance:
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
        return remittance


class MockGeneralLedger(LedgerInterface):
    def record_payment(self, entry: GeneralLedgerEntry) -> None:
        print("\n[MockLedger] Stage 5: Recording Revenue in General Ledger...")
        print(f"  -> SUCCESS! £{entry.credit_amount} recorded for {entry.invoice_id}.")