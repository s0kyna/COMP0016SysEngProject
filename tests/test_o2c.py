from datetime import date
from mock_company import MockCompany, MockGeneralLedger
from models import GeneralLedgerEntry, Invoice, InvoiceQAStatus


def test_o2c_success():
    # Initialize our company and our accounting book
    company = MockCompany()
    ledger = MockGeneralLedger()

    print("--- Starting O2C Cycle ---")

    # STAGE 1: Receive the Order
    # The buyer sends us a formal request to buy something.
    po = company.receive_purchase_order()
    
    # STAGE 2: Fulfillment & Delivery
    # The warehouse packs the items and ships them out.
    company.acknowledge_goods_are_sent(po.po_id)
    
    # The warehouse (or the buyer) confirms exactly what physically arrived.
    grn = company.receive_grn()

    # STAGE 3: Invoicing
    # We create the financial demand based on the PO and the GRN.
    # (In a real system, the 3-Way Match happens right before we send this!)
    draft_invoice = Invoice(
        invoice_id="INV-9901",
        po_id=po.po_id,
        grn_id=grn.grn_id,
        issue_date=date.today(),
        total_amount=po.expected_total,
        qa_status=InvoiceQAStatus.PENDING
    )
    company.send_invoice(draft_invoice)

    # STAGE 4: Cash Collection
    # The customer transfers money to our bank account.
    remittance = company.receive_payments()

    # STAGE 5: Recording Revenue
    # The CashApp agent verifies the bank transfer matches the invoice.
    # Once verified, we officially record the revenue in the accounting books.
    gl_entry = GeneralLedgerEntry(
        entry_id=f"GL-{draft_invoice.invoice_id}",
        date_recorded=date.today(),
        account_name="Product Sales Revenue",
        invoice_id=draft_invoice.invoice_id,
        credit_amount=remittance.amount_received
    )
    
    ledger.record_payment(gl_entry)

    print("--- O2C Cycle Complete ---")

test_o2c_success()