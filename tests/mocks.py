# tests/mocks.py
from datetime import datetime

from o2c_protocols import Company, Ledger, O2CController
from models import (
    BankRemittance,
    Customer,
    GRNStatus,
    GeneralLedgerEntry,
    GoodsReceivedNote,
    Invoice,
    PurchaseOrder,
    PurchaseOrderStatus,
    RemittanceStatus,
)
from db import get_session


class MockO2CController(O2CController):
    """Tracks O2C events for testing the workflow sequence."""

    def __init__(self):
        self.events = []

    def on_receive_purchase_order(self, po):
        self.events.append("po")

    def on_goods_sent(self, order_id):
        self.events.append("goods_sent")

    def on_receive_grn(self, grn):
        self.events.append("grn")

    def on_send_invoice(self, invoice):
        self.events.append("invoice")

    def on_receive_payments(self, payment):
        self.events.append("payment")

    def on_record_payment(self, entry):
        self.events.append("ledger_entry")

    def on_follow_up_with_customer(self, issue):
        self.events.append("follow_up_customer")

    def on_follow_up_with_warehouse(self, issue):
        self.events.append("follow_up_warehouse")

    def send_reminder_letter(self, invoice_id):
        self.events.append("dunning_reminder")

    def escalate_concerns(self, invoice_id):
        self.events.append("dunning_escalation")


class MockCompany(Company):
    """Mock ERP/company that stores O2C data in SQLite."""

    def __init__(self, event_tracker, session=None):
        self.event_tracker = event_tracker
        self.session = session or get_session()
        self._owns_session = session is None

    def close(self):
        if self._owns_session:
            self.session.close()

    def receive_purchase_order(self):
        print("[MockCompany] Stage 1: Receiving Purchase Order...")

        # Make sure the customer exists before creating the PO.
        customer = self.session.query(Customer).filter_by(
            customer_id=101
        ).first()

        if customer is None:
            customer = Customer(
                customer_id=101,
                company_name="ACME Corporation",
                billing_email="billing@acme.example",
                contact_email="contact@acme.example",
                credit_limit=50000.00,
            )
            self.session.add(customer)
            self.session.commit()

        po = self.session.query(PurchaseOrder).filter_by(
            po_id="PO-1001"
        ).first()

        if po is None:
            po = PurchaseOrder(
                po_id="PO-1001",
                customer_id=101,
                order_date=datetime.utcnow(),
                expected_total=25000.00,
                status=PurchaseOrderStatus.PENDING,
            )
            self.session.add(po)
            self.session.commit()

        print(f"  -> Received {po.po_id} for £{po.expected_total}")
        self.event_tracker.on_receive_purchase_order(po)

        return po

    def acknowledge_goods_are_sent(self, order_id):
        print(
            f"\n[MockCompany] Stage 2: "
            f"Warehouse is packing and shipping {order_id}..."
        )
        print("  -> Goods have successfully left the warehouse.")

        self.event_tracker.on_goods_sent(order_id)

    def receive_grn(self):
        print("\n[MockCompany] Stage 2b: Receiving Goods Received Note (GRN)...")

        grn = self.session.query(GoodsReceivedNote).filter_by(
            grn_id="GRN-5001"
        ).first()

        if grn is None:
            grn = GoodsReceivedNote(
                grn_id="GRN-5001",
                po_id="PO-1001",
                delivery_date=datetime.utcnow(),
                received_by_signature="Warehouse Dave",
                status=GRNStatus.FULL_DELIVERY,
            )
            self.session.add(grn)
            self.session.commit()

        print(f"  -> {grn.grn_id} logged. Status: {grn.status.name}")
        self.event_tracker.on_receive_grn(grn)

        return grn

    def send_invoice(self, invoice):
        print(
            f"\n[MockCompany] Stage 3: "
            f"Sending Invoice {invoice.invoice_id} to customer..."
        )
        print(
            f"  -> Billed for £{invoice.total_amount}. "
            f"QA Status: {invoice.qa_status.name}"
        )

        existing_invoice = self.session.query(Invoice).filter_by(
            invoice_id=invoice.invoice_id
        ).first()

        if existing_invoice is None:
            self.session.add(invoice)
            self.session.commit()

        self.event_tracker.on_send_invoice(invoice)

    def receive_payments(self):
        print("\n[MockCompany] Stage 4: Checking Bank Feed for payments...")

        remittance = self.session.query(BankRemittance).filter_by(
            payment_id="TXN-77881"
        ).first()

        if remittance is None:
            remittance = BankRemittance(
                payment_id="TXN-77881",
                payment_date=datetime.utcnow(),
                amount_received=25000.00,
                raw_bank_text="WIRE ACME CORP REF INV-9901",
                status=RemittanceStatus.UNPROCESSED,
                matched_invoice_id=None,
            )
            self.session.add(remittance)
            self.session.commit()

        print(f"  -> Received £{remittance.amount_received} from bank.")
        self.event_tracker.on_receive_payments(remittance)

        return remittance

    def follow_up_with_customer(self, message):
        print("\n[MockCompany] Exception: Generating email to Customer...")
        print(f"  -> Message: {message}")
        self.event_tracker.on_follow_up_with_customer(message)

    def follow_up_with_warehouse(self, message):
        print("\n[MockCompany] Exception: Generating email to Warehouse...")
        print(f"  -> Message: {message}")
        self.event_tracker.on_follow_up_with_warehouse(message)

    def send_reminder_letter(self, invoice_id):
        print(
            f"\n[MockCompany] Dunning Level 1: "
            f"Sending 7-day reminder for {invoice_id}..."
        )
        self.event_tracker.send_reminder_letter(invoice_id)

    def escalate_concerns(self, invoice_id):
        print(
            f"\n[MockCompany] Dunning Level 2: "
            f"Escalating 14-day unpaid invoice {invoice_id}..."
        )
        self.event_tracker.escalate_concerns(invoice_id)


class MockGeneralLedger(Ledger):
    """Mock ledger that stores entries in the SQLite database."""

    def __init__(self, event_tracker, session=None):
        self.event_tracker = event_tracker
        self.session = session or get_session()
        self._owns_session = session is None

    def close(self):
        if self._owns_session:
            self.session.close()

    def record_payment(self, entry):
        print("\n[MockLedger] Stage 5: Recording Revenue in General Ledger...")
        print(
            f"  -> SUCCESS! £{entry.credit_amount} "
            f"recorded for {entry.invoice_id}."
        )

        existing_entry = self.session.query(
            GeneralLedgerEntry
        ).filter_by(
            entry_id=entry.entry_id
        ).first()

        if existing_entry is None:
            self.session.add(entry)
            self.session.commit()

        self.event_tracker.on_record_payment(entry)