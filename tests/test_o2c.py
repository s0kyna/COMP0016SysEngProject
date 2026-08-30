from datetime import date

# Make sure to import the MockEventTracker!
from mock_company import MockCompany, MockGeneralLedger, MockEventTracker
from models import GeneralLedgerEntry, Invoice, InvoiceQAStatus

def test_o2c_success():
    # 1. Initialize the Event Tracker (The Audit Trail)
    event_tracker = MockEventTracker()
    
    # 2. Inject the tracker into our company and our accounting book (Dependency Injection!)
    company = MockCompany(event_tracker)
    ledger = MockGeneralLedger(event_tracker)

    print("--- Starting O2C Cycle ---")

    # STAGE 1: Receive the Order
    po = company.receive_purchase_order()
    # ✅ Check that the PO event fired
    assert event_tracker.events == ["po"], f"Test Failed: Expected ['po'], got {event_tracker.events}"
    
    # STAGE 2: Fulfillment & Delivery
    company.acknowledge_goods_are_sent(po.po_id)
    
    grn = company.receive_grn()
    # ✅ Check that the GRN event fired next
    assert event_tracker.events == ["po", "grn"], f"Test Failed: Expected ['po', 'grn'], got {event_tracker.events}"

    # STAGE 3: Invoicing
    draft_invoice = Invoice(
        invoice_id="INV-9901",
        po_id=po.po_id,
        grn_id=grn.grn_id,
        issue_date=date.today(),
        total_amount=po.expected_total,
        qa_status=InvoiceQAStatus.PENDING
    )
    company.send_invoice(draft_invoice)
    # ✅ Check that the Invoice event fired
    assert event_tracker.events == ["po", "grn", "invoice"]

    # STAGE 4: Cash Collection
    remittance = company.receive_payments()
    # ✅ Check that the Payment event fired
    assert event_tracker.events == ["po", "grn", "invoice", "payment"]

    # STAGE 5: Recording Revenue
    gl_entry = GeneralLedgerEntry(
        entry_id=f"GL-{draft_invoice.invoice_id}",
        date_recorded=date.today(),
        account_name="Product Sales Revenue",
        invoice_id=draft_invoice.invoice_id,
        credit_amount=remittance.amount_received
    )
    
    ledger.record_payment(gl_entry)
    # ✅ Check that the Final Ledger entry fired
    assert event_tracker.events == ["po", "grn", "invoice", "payment", "ledger_entry"]

    print("\n--- O2C Cycle Complete & Fully Audited ✅ ---")
    print("All assertions passed. The Event Tracker perfectly logged the sequence!")

if __name__ == "__main__":
    test_o2c_success()