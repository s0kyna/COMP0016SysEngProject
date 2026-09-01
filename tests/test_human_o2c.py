# test_o2c.py
from datetime import date
from mocks import MockCompany, MockGeneralLedger
from controller import HumanController
from human import Human
from models import GeneralLedgerEntry

def test_human_o2c_success():
    # 1. Setup the workers and controllers
    human = Human()
    controller = HumanController(human)
    
    # ✅ Check that the tracker starts completely empty
    assert controller.events == [], f"Expected empty tracker, got {controller.events}"
    
    # 2. Inject the controller into the system
    company = MockCompany(controller)
    ledger = MockGeneralLedger(controller)
    
    # 3. Connect the controller back to the system
    controller.set_company(company)

    print("--- Starting Controller-Driven O2C Cycle ---")

    # STAGE 1 & 2a: Receive Order & Send Goods
    # (Receiving the PO automatically triggers the controller to command the warehouse to send goods)
    po = company.receive_purchase_order()
    
    assert controller.current_po is not None
    assert controller.current_po.po_id == "PO-1001"
    # ✅ Audit Check: PO received, and Controller immediately sent goods
    assert controller.events == ["po", "goods_sent"]
    
    # STAGE 2b & 3: Receive GRN & Send Invoice
    # (Receiving GRN automatically triggers the Human to draft the invoice and send it)
    grn = company.receive_grn()

    assert grn.po_id == po.po_id
    # ✅ Audit Check: GRN received, Human matched it, Invoice sent
    assert controller.events == ["po", "goods_sent", "grn", "invoice"]

    # STAGE 4: Cash Collection
    remittance = company.receive_payments()
    assert remittance.amount_received > 0
    assert controller.events == ["po", "goods_sent", "grn", "invoice", "payment"]

    # STAGE 5: Recording Revenue
    gl_entry = GeneralLedgerEntry(
        entry_id=f"GL-INV-9901",
        date_recorded=date.today(),
        account_name="Product Sales Revenue",
        invoice_id="INV-9901",
        credit_amount=remittance.amount_received
    )
    ledger.record_payment(gl_entry)
    
    # ✅ Final Audit Check: All steps completed in exact order!
    assert controller.events == ["po", "goods_sent", "grn", "invoice", "payment", "ledger_entry"]

    print("\n--- O2C Cycle Complete & Fully Audited ✅ ---")

if __name__ == "__main__":
    test_human_o2c_success()