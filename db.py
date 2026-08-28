# Mock Database

# db.py
MOCK_PO = {
    "po_number": "PO-1001",
    "customer": "Acme Corp",
    "items": [{"item": "Industrial Widget V2", "qty": 10, "unit_price": 50.00}],
    "total": 500.00
}

MOCK_INVOICE = {
    "invoice_id": "INV-8088",
    "po_number": "PO-1001",
    "items": [{"item": "Ind. Widget Type B", "qty": 10, "unit_price": 55.00}],
    "total": 550.00
}