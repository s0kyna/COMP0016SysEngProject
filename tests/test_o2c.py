# tests/test_o2c.py
from datetime import datetime, timedelta

from tests.mocks import MockCompany, MockGeneralLedger, MockO2CController
from models import (
    GeneralLedgerEntry,
    Invoice,
    InvoiceQAStatus,
    InvoiceStatus,
)


def test_o2c_success():
    event_tracker = MockO2CController()

    assert event_tracker.events == []

    company = MockCompany(event_tracker)
    ledger = MockGeneralLedger(event_tracker)

    print("--- Starting O2C Cycle ---")

    # STAGE 1: Receive the Order
    po = company.receive_purchase_order()

    assert event_tracker.events == ["po"]

    # STAGE 2: Fulfilment & Delivery
    company.acknowledge_goods_are_sent(po.po_id)

    assert event_tracker.events == ["po", "goods_sent"]

    grn = company.receive_grn()

    assert event_tracker.events == [
        "po",
        "goods_sent",
        "grn",
    ]

    # STAGE 3: Invoicing
    draft_invoice = Invoice(
        invoice_id="INV-9901",
        po_id=po.po_id,
        grn_id=grn.grn_id,
        issue_date=datetime.utcnow(),
        due_date=datetime.utcnow() + timedelta(days=30),
        total_amount=po.expected_total,
        qa_status=InvoiceQAStatus.PENDING,
        status=InvoiceStatus.OUTSTANDING,
    )

    company.send_invoice(draft_invoice)

    assert event_tracker.events == [
        "po",
        "goods_sent",
        "grn",
        "invoice",
    ]

    # STAGE 4: Cash Collection
    remittance = company.receive_payments()

    assert event_tracker.events == [
        "po",
        "goods_sent",
        "grn",
        "invoice",
        "payment",
    ]

    # STAGE 5: Recording Revenue
    gl_entry = GeneralLedgerEntry(
        entry_id=f"GL-{draft_invoice.invoice_id}",
        date_recorded=datetime.utcnow(),
        account_name="Product Sales Revenue",
        invoice_id=draft_invoice.invoice_id,
        credit_amount=remittance.amount_received,
    )

    ledger.record_payment(gl_entry)

    assert event_tracker.events == [
        "po",
        "goods_sent",
        "grn",
        "invoice",
        "payment",
        "ledger_entry",
    ]

    print("\n--- O2C Cycle Complete & Fully Audited ✅ ---")
    print("All assertions passed!")


def test_o2c_failure():
    event_tracker = MockO2CController()
    company = MockCompany(event_tracker)

    assert event_tracker.events == []

    print("\n--- Starting O2C Cycle (FAILURE PATH) ---")

    # STAGE 1 & 2
    po = company.receive_purchase_order()
    company.acknowledge_goods_are_sent(po.po_id)
    grn = company.receive_grn()

    assert event_tracker.events == [
        "po",
        "goods_sent",
        "grn",
    ]

    # STAGE 3: 3-Way Match Failure
    print("\n[System] 🛑 CRITICAL MISMATCH DETECTED!")
    print(
        "[System] The GRN quantities do not match "
        "the expected PO quantities."
    )

    company.follow_up_with_customer(
        f"Discrepancy on {po.po_id}: "
        f"The expected total was £{po.expected_total}, "
        "but pricing is mismatched."
    )

    company.follow_up_with_warehouse(
        f"Discrepancy on {grn.grn_id}: "
        "Please physically recount the boxes on the dock."
    )

    assert event_tracker.events == [
        "po",
        "goods_sent",
        "grn",
        "follow_up_customer",
        "follow_up_warehouse",
    ]

    print("\n--- O2C Cycle Halted & Exceptions Audited ✅ ---")
    print("All assertions passed!")


if __name__ == "__main__":
    print("Running Success Path...")
    test_o2c_success()

    print("\n" + "=" * 50)

    print("Running Failure Path...")
    test_o2c_failure()