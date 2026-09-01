# test_o2c.py
from mocks import MockCompany, MockGeneralLedger
from controller import HumanController
from human import Human

def test_human_o2c_success():
    # 1. Setup the workers and controllers
    human = Human()
    controller = HumanController(human)
    
    # 2. Inject the controller into the system
    company = MockCompany(controller)
    ledger = MockGeneralLedger(controller)
    
    # 3. Connect the controller back to the system
    controller.set_company(company)

    print("--- Starting Controller-Driven O2C Cycle ---")

    # STAGE 1: Receive the Order
    # (This will automatically trigger acknowledge_goods_are_sent via the controller)
    po = company.receive_purchase_order()
    
    # Assert the controller stored the PO in memory
    assert controller.current_po is not None
    assert controller.current_po.po_id == "PO-1001"
    
    # STAGE 2: Fulfillment & Delivery
    # (This will automatically trigger the Human to draft the invoice and do the match)
    grn = company.receive_grn()

    # Assert that the GRN is valid
    assert grn.po_id == po.po_id

    # STAGE 4: Cash Collection
    remittance = company.receive_payments()
    assert remittance.amount_received > 0

    print("\n--- O2C Cycle Complete & Fully Audited ✅ ---")

if __name__ == "__main__":
    test_human_o2c_success()