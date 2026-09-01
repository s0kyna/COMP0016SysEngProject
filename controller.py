# controller.py
from o2c_protocols import Company, O2CController # We use EventTracker blueprint as our O2CController
from models import PurchaseOrder, GoodsReceivedNote
from human import Human

class HumanController(O2CController):
    """
    Actively drives the O2C pipeline, relying on a Human for cognitive tasks.
    """
    def __init__(self, human: Human):
        self.human = human
        self.company = None
        self.current_po = None  # The controller needs memory to hold the PO!
    
    def set_company(self, company: Company):
        self.company = company # Fixed: lowercase 'company'

    def on_receive_purchase_order(self, po: PurchaseOrder):
        # Save to memory for later
        self.current_po = po 
        # Command the company to proceed to the next step
        self.company.acknowledge_goods_are_sent(po.po_id) # Fixed: po_id

    def on_receive_grn(self, grn: GoodsReceivedNote):
        # Human drafts the invoice
        invoice = self.human.get_invoice(grn)
        
        # Human does the 3-way match
        if self.human.is_matching(self.current_po, grn, invoice):
            print("  🎉 [Controller] YIPPEEEE it matches!! Sending invoice.")
            self.company.send_invoice(invoice)
        else:
            print("  🛑 [Controller] MATCH FAILED. Halting pipeline.")
            # Human gets angry and writes complaints
            customer_complaint = self.human.complain("Price mismatch with Customer")
            warehouse_complaint = self.human.complain("Missing items from Warehouse")
            
            # (Assuming you add these methods to your MockCompany)
            # self.company.follow_up_with_customer(customer_complaint)
            # self.company.follow_up_with_warehouse(warehouse_complaint)
            
    # (You would also implement on_receive_payments and on_record_payment here)
    def on_receive_payments(self, payment): pass
    def on_send_invoice(self, invoice): pass
    def on_record_payment(self, entry): pass