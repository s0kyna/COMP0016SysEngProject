from datetime import date

# Make sure to import the MockEventTracker!
from mocks import MockCompany, MockGeneralLedger, MockO2CController
from models import GeneralLedgerEntry, Invoice, InvoiceQAStatus

def test_o2c_success():
    # 1. Initialize the Event Tracker (The Audit Trail)
    event_tracker = MockO2CController()
    
    # ✅ Check that the tracker is completely empty at the start
    assert event_tracker.events == [], f"Test Failed: Expected empty tracker, got {event_tracker.events}"
    
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
    
    # ✅ Check that the Goods Sent event fired
    assert event_tracker.events == ["po", "goods_sent"], f"Test Failed: Expected ['po', 'goods_sent'], got {event_tracker.events}"
    
    grn = company.receive_grn()
    
    # ✅ Check that the GRN event fired next
    assert event_tracker.events == ["po", "goods_sent", "grn"], f"Test Failed: Expected ['po', 'goods_sent', 'grn'], got {event_tracker.events}"

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
    assert event_tracker.events == ["po", "goods_sent", "grn", "invoice"]

    # STAGE 4: Cash Collection
    remittance = company.receive_payments()
    
    # ✅ Check that the Payment event fired
    assert event_tracker.events == ["po", "goods_sent", "grn", "invoice", "payment"]

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
    assert event_tracker.events == ["po", "goods_sent", "grn", "invoice", "payment", "ledger_entry"]

    print("\n--- O2C Cycle Complete & Fully Audited ✅ ---")
    print("All assertions passed. The Event Tracker perfectly logged the sequence!")



def test_o2c_failure():
    # 1. Initialize our clean tracker and systems
    event_tracker = MockO2CController()
    company = MockCompany(event_tracker)
    
    assert event_tracker.events == [], "Test Failed: Tracker should be empty."

    print("\n--- Starting O2C Cycle (FAILURE PATH) ---")

    # STAGE 1 & 2: Receive Order, Send Goods, Receive GRN
    po = company.receive_purchase_order()
    company.acknowledge_goods_are_sent(po.po_id)
    grn = company.receive_grn()

    # ✅ Audit Check: Verify normal operations up to this point
    assert event_tracker.events == ["po", "goods_sent", "grn"]

    # STAGE 3: THE DISCREPANCY (3-Way Match Fails!)
    print("\n[System] 🛑 CRITICAL MISMATCH DETECTED!")
    print("[System] The GRN quantities do not match the expected PO quantities. Halting pipeline.")
    
    # Instead of generating an invoice, the system triggers exception handling
    company.follow_up_with_customer(f"Discrepancy on {po.po_id}: The expected total was £{po.expected_total}, but pricing is mismatched.")
    company.follow_up_with_warehouse(f"Discrepancy on {grn.grn_id}: Please physically recount the boxes on the dock.")

    # ✅ Final Audit Check: Verify the complaints were logged INSTEAD of an invoice!
    assert event_tracker.events == [
        "po", 
        "goods_sent", 
        "grn", 
        "follow_up_customer", 
        "follow_up_warehouse"
    ], f"Test Failed: Expected complaint events, got {event_tracker.events}"

    print("\n--- O2C Cycle Halted & Exceptions Audited ✅ ---")
    print("All assertions passed. The tracker successfully logged the failures!")


if __name__ == "__main__":
    print("Running Success Path...")
    test_o2c_success()
    
    print("\n" + "="*50)
    
    print("Running Failure Path...")
    test_o2c_failure()
