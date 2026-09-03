from o2c_protocols import Company, O2CController
from models import PurchaseOrder, GoodsReceivedNote
from human import Human


class HumanController(O2CController):
    def __init__(self, human: Human):
        self.human = human
        self.company = None
        self.current_po = None
        self.events = []

    def set_company(self, company: Company):
        self.company = company

    def on_receive_purchase_order(self, po: PurchaseOrder):
        self.events.append("po")
        self.current_po = po
        self.company.acknowledge_goods_are_sent(po.po_id)

    def on_goods_sent(self, order_id: str):
        self.events.append("goods_sent")

    def on_receive_grn(self, grn: GoodsReceivedNote):
        self.events.append("grn")

        invoice = self.human.get_invoice(grn)

        if self.human.is_matching(self.current_po, grn, invoice):
            print("  🎉 [Controller] YIPPEEEE it matches!! Sending invoice.")
            self.company.send_invoice(invoice)
        else:
            print("  🛑 [Controller] MATCH FAILED. Halting pipeline.")

            complaint = self.human.complain("Mismatch detected!")

            self.company.follow_up_with_customer(complaint.message)
            self.company.follow_up_with_warehouse(
                "Please physically recount the items."
            )

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



import asyncio
from agents.invoice_qa import run_invoice_qa
from agents.cash_application import run_cash_application
from agents.dunning import run_dunning


class AgentController(O2CController):
    def __init__(self):
        self.events = []

    async def process_invoice(self, invoice_id):
        print(f"\n=== CONTROLLER: Invoice {invoice_id} ===")
        result = await run_invoice_qa(invoice_id)

        if result["human_review_required"]:
            self.events.append("invoice_qa_human_review")
            print("Invoice sent to human QA review.")
            return False

        self.events.append("invoice_qa_complete")
        print("Invoice QA complete. O2C may continue.")
        return True

    async def process_payment(self, payment_id):
        print(f"\n=== CONTROLLER: Payment {payment_id} ===")
        result = await run_cash_application(payment_id)

        if result["decision"] == "HUMAN_REVIEW":
            self.events.append("cash_application_human_review")
            print("Payment sent to human cash application review.")
            return False

        self.events.append("payment_matched")
        print(f"Payment matched to {result['invoice_id']}.")
        return True

    async def process_dunning(self, invoice_id):
        print(f"\n=== CONTROLLER: Dunning {invoice_id} ===")
        result = await run_dunning(invoice_id)

        if result["action"] == "NO_ACTION":
            self.events.append("dunning_not_required")

        elif result["action"] == "HUMAN_REVIEW":
            self.events.append("dunning_human_review")
            print("Dunning case sent to human review.")

        elif result["action"] == "WAIT":
            self.events.append("dunning_wait")
            print("Dunning agent decided to wait.")

        elif result["action"] == "SEND_REMINDER":
            self.events.append("dunning_reminder")
            print("Dunning reminder sent.")

        return result

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