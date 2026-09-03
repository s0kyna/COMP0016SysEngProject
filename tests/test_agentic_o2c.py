import pytest
from unittest.mock import AsyncMock, patch
from controller import AgentController


@pytest.mark.asyncio
async def test_invoice_qa_success():
    controller = AgentController()

    fake_result = {
        "decision": "ACCEPT",
        "human_review_required": False
    }

    with patch(
        "controller.run_invoice_qa",
        new=AsyncMock(return_value=fake_result)
    ):
        result = await controller.process_invoice("INV-9901")

    assert result is True
    assert controller.events == ["invoice_qa_complete"]


@pytest.mark.asyncio
async def test_invoice_qa_human_review():
    controller = AgentController()

    fake_result = {
        "decision": "HUMAN_REVIEW",
        "human_review_required": True
    }

    with patch(
        "controller.run_invoice_qa",
        new=AsyncMock(return_value=fake_result)
    ):
        result = await controller.process_invoice("INV-9901")

    assert result is False
    assert controller.events == ["invoice_qa_human_review"]


@pytest.mark.asyncio
async def test_cash_application():
    controller = AgentController()

    fake_result = {
        "decision": "MATCH",
        "invoice_id": "INV-9901",
        "confidence": 0.95
    }

    with patch(
        "controller.run_cash_application",
        new=AsyncMock(return_value=fake_result)
    ):
        result = await controller.process_payment("PAY-77881")

    assert result is True
    assert controller.events == ["payment_matched"]

@pytest.mark.asyncio
async def test_cash_application_human_review():
    controller = AgentController()

    fake_result = {
        "decision": "HUMAN_REVIEW",
        "invoice_id": "NONE",
        "confidence": 0.4,
        "reason": "Multiple invoices are plausible."
    }

    with patch(
        "controller.run_cash_application",
        new=AsyncMock(return_value=fake_result)
    ):
        result = await controller.process_payment("PAY-77881")

    assert result is False
    assert controller.events == ["cash_application_human_review"]

@pytest.mark.asyncio
async def test_dunning_wait():
    controller = AgentController()

    fake_result = {
        "action": "WAIT",
        "confidence": 0.9,
        "risk": "MEDIUM",
        "reason": "Customer has provided a credible near-term payment promise.",
        "message": "NONE"
    }

    with patch(
        "controller.run_dunning",
        new=AsyncMock(return_value=fake_result)
    ):
        result = await controller.process_dunning("INV-9901")

    assert result["action"] == "WAIT"
    assert controller.events == ["dunning_wait"]
    
@pytest.mark.asyncio
async def test_dunning_human_review():
    controller = AgentController()

    fake_result = {
        "action": "HUMAN_REVIEW",
        "confidence": 0.9,
        "risk": "HIGH"
    }

    with patch(
        "controller.run_dunning",
        new=AsyncMock(return_value=fake_result)
    ):
        await controller.process_dunning("INV-9901")

    assert controller.events == ["dunning_human_review"]