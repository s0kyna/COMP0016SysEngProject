# agents/planner.py
def get_next_job(db):
    """Fetches the next PO/Invoice pair to process."""
    return {"po": db.MOCK_PO, "invoice": db.MOCK_INVOICE}