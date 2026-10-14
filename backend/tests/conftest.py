import os
import tempfile

from cryptography.fernet import Fernet

# Must be set before `app` is imported: settings and the DB engine are created at import time.
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["SECRET_KEY"] = Fernet.generate_key().decode()

import pytest  # noqa: E402

from app.db import Base, engine  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def fake_llm(monkeypatch):
    """Replace the network call with queued replies; records the models used."""
    from app import llm

    state = {"replies": [], "models": []}

    def _complete(cfg, messages, max_tokens):
        state["models"].append(cfg.litellm_model)
        return state["replies"].pop(0)

    monkeypatch.setattr(llm, "_complete", _complete)
    return state
