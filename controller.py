# controller.py
from o2c_protocols import Company, O2CController
from models import PurchaseOrder, GoodsReceivedNote
from human import Human

class HumanController(O2CController):
    def __init__(self, human: Human):
        self.human = human
        self.company = None
        self.current_po = None
        self.events = []  # Tracking array
    
    def set_company(self, company: Company):
        self.company = company

    def on_receive_purchase_order(self, po: PurchaseOrder):
        self.events.append("po")
        self.current_po = po 
        self.company.acknowledge_goods_are_sent(po.po_id)

    # 🚨 ADDED: Missing on_goods_sent method
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
            
            # 🚨 Make sure these two lines are added! 
            # This is what triggers the tracker to log 'follow_up_customer' and 'follow_up_warehouse'
            self.company.follow_up_with_customer(complaint.message)
            self.company.follow_up_with_warehouse("Please physically recount the items.")
            
    def on_send_invoice(self, invoice):
        self.events.append("invoice")
        
    def on_receive_payments(self, payment):
        self.events.append("payment")
        
    def on_record_payment(self, entry):
        self.events.append("ledger_entry")

    # 🚨 ADDED: Missing follow_up methods
    def on_follow_up_with_customer(self, issue: str):
        self.events.append("follow_up_customer")

    def on_follow_up_with_warehouse(self, issue: str):
        self.events.append("follow_up_warehouse")

    def on_dunning_reminder(self, invoice_id: str):
        self.events.append("dunning_reminder")

    def on_dunning_escalation(self, invoice_id: str):
        self.events.append("dunning_escalation")