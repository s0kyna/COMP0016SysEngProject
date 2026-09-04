import sys
import types

# Allow the deterministic/unit test suite to run on machines that have not
# installed Microsoft Agent Framework. Live AI calls are mocked in tests.
try:
    import agent_framework  # noqa: F401
except ModuleNotFoundError:
    af = types.ModuleType("agent_framework")
    afo = types.ModuleType("agent_framework.openai")

    class DummyAgent:
        def __init__(self, *args, **kwargs):
            pass

    class DummyClient:
        def __init__(self, *args, **kwargs):
            pass

    af.Agent = DummyAgent
    afo.OpenAIChatCompletionClient = DummyClient
    sys.modules["agent_framework"] = af
    sys.modules["agent_framework.openai"] = afo

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models import Base


@pytest.fixture
def db_session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    try:
        yield Session
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def patch_db(monkeypatch, db_session_factory):
    """Route agent/API get_session() calls to an isolated in-memory DB."""
    import api
    import agents.invoice_qa as invoice_qa
    import agents.cash_application as cash_application
    import agents.dunning as dunning

    getter = lambda: db_session_factory()
    monkeypatch.setattr(api, "get_session", getter)
    monkeypatch.setattr(invoice_qa, "get_session", getter)
    monkeypatch.setattr(cash_application, "get_session", getter)
    monkeypatch.setattr(dunning, "get_session", getter)
    return db_session_factory


@pytest.fixture(autouse=True)
def isolate_legacy_mock_database(monkeypatch, db_session_factory):
    """Keep the original prototype mock tests off the real project database."""
    try:
        import tests.mocks as mocks
    except ImportError:
        yield
        return
    monkeypatch.setattr(mocks, "get_session", lambda: db_session_factory())
    yield
