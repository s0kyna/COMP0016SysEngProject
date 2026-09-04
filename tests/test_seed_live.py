import pytest
from models import (
    AgentAction, BankRemittance, HumanReviewCase, PaymentApplication,
    RemittanceStatus,
)
import seed_data


def test_seed_contains_unprocessed_live_cash_case(monkeypatch, db_session_factory):
    monkeypatch.setattr(seed_data, "initialize_database", lambda: None)
    monkeypatch.setattr(seed_data, "get_session", lambda: db_session_factory())
    seed_data.seed()

    s = db_session_factory()
    payment = s.query(BankRemittance).filter_by(payment_id="PAY-LIVE-001").one()
    assert payment.status == RemittanceStatus.UNPROCESSED
    assert payment.matched_invoice_id is None
    assert s.query(PaymentApplication).filter_by(payment_id="PAY-LIVE-001").count() == 0
    assert s.query(AgentAction).filter_by(entity_id="PAY-LIVE-001").count() == 0
    assert s.query(HumanReviewCase).filter_by(entity_id="PAY-LIVE-001").count() == 0
    s.close()


def test_seed_live_ai_cases_start_without_agent_outcomes(monkeypatch, db_session_factory):
    monkeypatch.setattr(seed_data, "initialize_database", lambda: None)
    monkeypatch.setattr(seed_data, "get_session", lambda: db_session_factory())
    seed_data.seed()

    s = db_session_factory()
    for entity_id in ("INV-LIVE-001", "INV-LIVE-002"):
        assert s.query(AgentAction).filter_by(entity_id=entity_id).count() == 0
        assert s.query(HumanReviewCase).filter_by(entity_id=entity_id).count() == 0
    s.close()


def test_seed_live_invoice_qa_starts_pending(monkeypatch, db_session_factory):
    from models import Invoice, InvoiceQAStatus
    monkeypatch.setattr(seed_data, "initialize_database", lambda: None)
    monkeypatch.setattr(seed_data, "get_session", lambda: db_session_factory())
    seed_data.seed()

    s = db_session_factory()
    invoice = s.query(Invoice).filter_by(invoice_id="INV-LIVE-001").one()
    assert invoice.qa_status == InvoiceQAStatus.PENDING
    s.close()


@pytest.mark.asyncio
async def test_actual_live_cash_seed_processes_without_ai(monkeypatch, db_session_factory):
    from agents import cash_application
    from models import Invoice, InvoiceStatus
    from unittest.mock import AsyncMock

    monkeypatch.setattr(seed_data, "initialize_database", lambda: None)
    monkeypatch.setattr(seed_data, "get_session", lambda: db_session_factory())
    monkeypatch.setattr(cash_application, "get_session", lambda: db_session_factory())
    seed_data.seed()

    ai = AsyncMock()
    monkeypatch.setattr(cash_application, "run_ai_match", ai)
    result = await cash_application.run_cash_application("PAY-LIVE-001")

    ai.assert_not_awaited()
    assert result["decision"] == "MATCH"
    assert len(result["allocations"]) == 2

    s = db_session_factory()
    payment = s.query(BankRemittance).filter_by(payment_id="PAY-LIVE-001").one()
    assert payment.status == RemittanceStatus.MATCHED_AUTO
    assert s.query(PaymentApplication).filter_by(payment_id="PAY-LIVE-001").count() == 2
    assert s.query(AgentAction).filter_by(entity_id="PAY-LIVE-001", decision="MATCH").count() == 1
    assert s.query(Invoice).filter(Invoice.invoice_id.in_(["INV-LIVE-101", "INV-LIVE-102"]), Invoice.status == InvoiceStatus.PAID).count() == 2
    s.close()
