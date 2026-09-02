# tests/test_human_o2c.py

from datetime import datetime

from tests.mocks import MockCompany, MockGeneralLedger
from controller import HumanController
from human import Human
from models import GeneralLedgerEntry


def test_human_o2c_success():
    human = Human()
    controller = HumanController(human)

    assert controller.events == []

    company = MockCompany(controller)
    ledger = MockGeneralLedger(controller)

    controller.set_company(company)

    print("--- Starting Controller-Driven O2C Cycle (SUCCESS PATH) ---")

    po = company.receive_purchase_order()

    assert controller.events == [
        "po",
        "goods_sent",
    ]

    grn = company.receive_grn()

    assert controller.events == [
        "po",
        "goods_sent",
        "grn",
        "invoice",
    ]

    remittance = company.receive_payments()

    assert controller.events == [
        "po",
        "goods_sent",
        "grn",
        "invoice",
        "payment",
    ]

    gl_entry = GeneralLedgerEntry(
        entry_id="GL-INV-9901-HUMAN",
        date_recorded=datetime.utcnow(),
        account_name="Product Sales Revenue",
        invoice_id="INV-9901",
        credit_amount=remittance.amount_received,
    )

    ledger.record_payment(gl_entry)

    assert controller.events == [
        "po",
        "goods_sent",
        "grn",
        "invoice",
        "payment",
        "ledger_entry",
    ]

    print("\n--- Human O2C Success Path Complete ✅ ---")


def test_human_o2c_failure():
    human = Human()
    controller = HumanController(human)

    assert controller.events == []

    company = MockCompany(controller)
    controller.set_company(company)

    print("--- Starting Controller-Driven O2C Cycle (FAILURE PATH) ---")

    po = company.receive_purchase_order()

    print(
        "  🕵️ [Test Injection] "
        "Mutating PO price to £99,999 to force a failure..."
    )

    controller.current_po.expected_total = 99999.00

    grn = company.receive_grn()

    assert controller.events == [
        "po",
        "goods_sent",
        "grn",
        "follow_up_customer",
        "follow_up_warehouse",
    ]

    print("\n--- Human O2C Failure Path Complete ✅ ---")


def test_human_o2c_dunning_flow():
    human = Human()
    controller = HumanController(human)

    company = MockCompany(controller)
    ledger = MockGeneralLedger(controller)

    controller.set_company(company)

    print("\n--- Starting Human O2C Dunning Path ---")

    po = company.receive_purchase_order()
    company.receive_grn()

    assert controller.events == [
        "po",
        "goods_sent",
        "grn",
        "invoice",
    ]

    print("\n[System Clock] ⏰ 7 Days have passed without payment...")

    company.send_reminder_letter("INV-9901")

    assert controller.events == [
        "po",
        "goods_sent",
        "grn",
        "invoice",
        "dunning_reminder",
    ]

    print("\n[System Clock] ⏰ 14 Days have passed without payment...")

    company.escalate_concerns("INV-9901")

    assert controller.events == [
        "po",
        "goods_sent",
        "grn",
        "invoice",
        "dunning_reminder",
        "dunning_escalation",
    ]

    print("\n[Customer] Apologies, sending late payment now.")

    remittance = company.receive_payments()

    gl_entry = GeneralLedgerEntry(
        entry_id="GL-INV-9901-LATE",
        date_recorded=datetime.utcnow(),
        account_name="Product Sales Revenue",
        invoice_id="INV-9901",
        credit_amount=remittance.amount_received,
    )

    ledger.record_payment(gl_entry)

    assert controller.events == [
        "po",
        "goods_sent",
        "grn",
        "invoice",
        "dunning_reminder",
        "dunning_escalation",
        "payment",
        "ledger_entry",
    ]

    print("\n--- Human Dunning Cycle Complete & Fully Audited ✅ ---")


if __name__ == "__main__":
    test_human_o2c_success()
    print("=" * 60)
    test_human_o2c_failure()
    print("=" * 60)
    test_human_o2c_dunning_flow()