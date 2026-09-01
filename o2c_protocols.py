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
    Interface for tracking critical business milestones (Audit Trail).
    """
    @abstractmethod
    def on_receive_purchase_order(self, po: PurchaseOrder) -> None:
        pass
    
    @abstractmethod
    def on_receive_grn(self, grn: GoodsReceivedNote) -> None: 
        pass
    
    @abstractmethod
    def on_receive_payments(self, payment: BankRemittance) -> None:
        pass
    
    @abstractmethod
    def on_send_invoice(self, invoice: Invoice) -> None:
        pass
        
    @abstractmethod
    def on_record_payment(self, entry: GeneralLedgerEntry) -> None:
        pass


class Company(ABC):
    """
    The interface defining the required O2C steps. 
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


class Ledger(ABC):
    """
    The interface for recording revenue.
    """
    @abstractmethod
    def record_payment(self, entry: GeneralLedgerEntry) -> None:
        pass