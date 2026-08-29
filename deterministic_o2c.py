from abc import ABC, abstractmethod
from datetime import date
from models import *

# ==========================================
# 1. THE INTERFACES (The Blueprints)
# ==========================================

class CompanyInterface(ABC):
    """
    The interface defining the required O2C steps. 
    Any company system (Legacy or Agentic) must implement these exact methods.
    """
    
    @abstractmethod
    def receive_purchase_order(self) -> PurchaseOrder:
        pass

    @abstractmethod
    def acknowledge_goods_are_sent(self, order_id: str) -> None:
        pass

    @abstractmethod
    def recieve_grn(self) -> GoodsReceivedNote:
        pass

    @abstractmethod
    def send_invoice(self, invoice: Invoice) -> None:
        pass

    @abstractmethod
    def recieve_payments(self) -> BankRemittance:
        pass


class LedgerInterface(ABC):
    """
    The interface for recording revenue.
    """
    @abstractmethod
    def record_payment(self, entry: GeneralLedgerEntry) -> None:
        pass