# tests/test_o2c.py
import pytest
import db
from agents.planner import get_next_job
from agents.supervisor import enforce_rules
from agents.invoice_qa import analyze_invoice_qa

def test_planner_fetches_jobs():
    """Test that the planner successfully pulls the mock PO and Invoice."""
    job = get_next_job(db)
    assert "po" in job
    assert "invoice" in job
    assert job["po"]["po_number"] == "PO-1001"

def test_supervisor_rejects_mismatches():
    """Test that the supervisor correctly blocks an invoice if QA flags it."""
    # Simulating the QA agent finding a mismatch
    decision = enforce_rules(amount=500.00, qa_status="MISMATCH_DETECTED")
    assert decision["action"] == "REJECT"

def test_supervisor_escalates_high_amounts():
    """Test that the supervisor catches amounts over the threshold (500)."""
    # Simulating a matched invoice but with a high monetary value
    decision = enforce_rules(amount=1000.00, qa_status="MATCH")
    assert decision["action"] == "ESCALATE"

def test_supervisor_approves_clean_invoices():
    """Test the happy path where everything matches and amount is under threshold."""
    decision = enforce_rules(amount=450.00, qa_status="MATCH")
    assert decision["action"] == "APPROVE"

def test_mock_qa_agent_output(monkeypatch):
    """Test the QA agent's fallback logic (when no API key is present)."""
    # Temporarily remove API key if it exists to test the mock fallback
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    
    result = analyze_invoice_qa(db.MOCK_PO, db.MOCK_INVOICE)
    assert result["status"] == "MISMATCH_DETECTED"
    assert "findings" in result