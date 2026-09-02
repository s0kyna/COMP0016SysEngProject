# o2c_protocols.py
from abc import ABC, abstractmethod
from models import (
    PurchaseOrder, GoodsReceivedNote, 
    BankRemittance, Invoice, GeneralLedgerEntry
)

# ==========================================
# THE BLUEPRINTS (Interfaces)
# ==========================================

class O2CController(ABC):
    """
    Interface for actively controlling and tracking critical business milestones.
    Every event in the pipeline must trigger one of these methods.
    """
    @abstractmethod
    def on_receive_purchase_order(self, po: PurchaseOrder) -> None:
        pass
    
    @abstractmethod
    def on_goods_sent(self, order_id: str) -> None:
        pass
    
    @abstractmethod
    def on_receive_grn(self, grn: GoodsReceivedNote) -> None: 
        pass
    
    @abstractmethod
    def on_send_invoice(self, invoice: Invoice) -> None:
        pass

    @abstractmethod
    def on_receive_payments(self, payment: BankRemittance) -> None:
        pass
        
    @abstractmethod
    def on_record_payment(self, entry: GeneralLedgerEntry) -> None:
        pass

    # --- Exception Tracking (When things go wrong) ---
    @abstractmethod
    def on_follow_up_with_customer(self, issue: str) -> None:
        pass

    @abstractmethod
    def on_follow_up_with_warehouse(self, issue: str) -> None:
        pass
    # Add to Company class in o2c_protocols.py
    @abstractmethod
    def send_reminder_letter(self, invoice_id: str) -> None:
        pass

    @abstractmethod
    def escalate_concerns(self, invoice_id: str) -> None:
        pass


class Company(ABC):
    """
    The interface defining the required O2C system actions. 
    """
    @abstractmethod
    def receive_purchase_order(self) -> PurchaseOrder:
        pass

    @abstractmethod
    def acknowledge_goods_are_sent(self, order_id: str) -> None:
        pass

    @abstractmethod
    def receive_grn(self) -> GoodsReceivedNote:
        pass

    @abstractmethod
    def send_invoice(self, invoice: Invoice) -> None:
        pass

    @abstractmethod
    def receive_payments(self) -> BankRemittance:
        pass

    # --- Exception Handling Actions ---
    @abstractmethod
    def follow_up_with_customer(self, message: str) -> None:
        pass

    @abstractmethod
    def follow_up_with_warehouse(self, message: str) -> None:
        pass


class Ledger(ABC):
    """
    The interface for recording revenue.
    """
    @abstractmethod
    def record_payment(self, entry: GeneralLedgerEntry) -> None:
        pass