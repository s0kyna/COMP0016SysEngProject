# test_o2c.py
from datetime import date
from mocks import MockCompany, MockGeneralLedger
from controller import HumanController
from human import Human
from models import GeneralLedgerEntry

def test_human_o2c_success():
    human = Human()
    controller = HumanController(human)
    assert controller.events == [], f"Expected empty tracker, got {controller.events}"
    
    company = MockCompany(controller)
    ledger = MockGeneralLedger(controller)
    controller.set_company(company)

    print("--- Starting Controller-Driven O2C Cycle (SUCCESS PATH) ---")

    # STAGE 1 & 2a
    po = company.receive_purchase_order()
    assert controller.events == ["po", "goods_sent"]
    
    # STAGE 2b & 3
    grn = company.receive_grn()
    assert controller.events == ["po", "goods_sent", "grn", "invoice"]

    # STAGE 4
    remittance = company.receive_payments()
    assert controller.events == ["po", "goods_sent", "grn", "invoice", "payment"]

    # STAGE 5
    gl_entry = GeneralLedgerEntry(
        entry_id=f"GL-INV-9901",
        date_recorded=date.today(),
        account_name="Product Sales Revenue",
        invoice_id="INV-9901",
        credit_amount=remittance.amount_received
    )
    ledger.record_payment(gl_entry)
    
    assert controller.events == ["po", "goods_sent", "grn", "invoice", "payment", "ledger_entry"]
    print("\n--- O2C Cycle Complete & Fully Audited ✅ ---\n")


def test_human_o2c_failure():
    human = Human()
    controller = HumanController(human)
    assert controller.events == []

    company = MockCompany(controller)
    controller.set_company(company)

    print("--- Starting Controller-Driven O2C Cycle (FAILURE PATH) ---")

    # STAGE 1 & 2a
    po = company.receive_purchase_order()
    
    # 🚨 DATA MUTATION INJECTION: 
    # We silently corrupt the PO data in the controller's memory to simulate a pricing error!
    print("  🕵️ [Test Injection] Mutating PO price to £99,999 to force a failure...")
    controller.current_po.expected_total = 99999.00 

    # STAGE 2b: GRN arrives, which triggers the Human matching process
    grn = company.receive_grn()

    # ✅ Audit Check: Verify the pipeline halted and the complaints were logged!
    assert controller.events == [
        "po", 
        "goods_sent", 
        "grn", 
        "follow_up_customer", 
        "follow_up_warehouse"
    ], f"Test Failed: Expected complaint events, got {controller.events}"

    print("\n--- O2C Cycle Halted & Exceptions Audited ✅ ---")


if __name__ == "__main__":
    test_human_o2c_success()
    print("="*60 + "\n")
    test_human_o2c_failure()