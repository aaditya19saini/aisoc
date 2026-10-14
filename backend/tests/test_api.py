import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import google_client, projects
from app.db import SessionLocal
from app.main import app
from app.models import Email

client = TestClient(app)

PROJECT = {"project": "Acme rollout", "status": "At risk", "stakeholder_name": "Priya", "stakeholder_email": "priya@acme.com", "auto_send": True}


@pytest.fixture
def google(monkeypatch):
    """Pretend Google is connected; capture drafts/sends instead of calling Gmail."""
    calls = []
    monkeypatch.setattr(google_client, "is_connected", lambda db: True)
    monkeypatch.setattr(google_client, "create_draft", lambda db, to, s, b: calls.append(("draft", to)) or "d1")
    monkeypatch.setattr(google_client, "send_email", lambda db, to, s, b: calls.append(("send", to)) or "s1")
    monkeypatch.setattr(projects, "load_projects", lambda db: [dict(PROJECT), {**PROJECT, "project": "Website", "auto_send": False}])
    from app.store import set_setting

    set_setting(SessionLocal(), "sheet.id", "sheet123")
    return calls


def test_settings_masks_api_key_and_keeps_it_when_omitted():
    r = client.put("/api/settings/models/classifier", json={"provider": "openai", "model": "gpt-x", "api_key": "sk-abcd1234"})
    m = r.json()["models"]["classifier"]
    assert m == {"provider": "openai", "model": "gpt-x", "api_base": "", "has_key": True, "key_hint": "…1234"}
    assert "sk-abcd1234" not in r.text
    r = client.put("/api/settings/models/classifier", json={"provider": "gemini", "model": "gemini-x"})
    assert r.json()["models"]["classifier"]["has_key"] is True


def test_switching_model_takes_effect_without_restart(fake_llm):
    fake_llm["replies"] = ["OK", "OK"]
    client.put("/api/settings/models/writer", json={"provider": "anthropic", "model": "claude-sonnet-5-5"})
    assert client.post("/api/settings/models/writer/test").json()["ok"]
    client.put("/api/settings/models/writer", json={"provider": "ollama", "model": "llama3.1", "api_base": "http://localhost:11434"})
    client.post("/api/settings/models/writer/test")
    assert fake_llm["models"] == ["anthropic/claude-sonnet-5-5", "ollama/llama3.1"]


def test_unknown_provider_rejected():
    assert client.put("/api/settings/models/writer", json={"provider": "nope", "model": "x"}).status_code == 400


def test_draft_always_allowed_send_guarded(google):
    base = {"subject": "Update", "body": "Hi"}
    assert client.post("/api/outbound", json={**base, "project": "Website", "to": "x@y.com", "mode": "draft"}).status_code == 200
    # Auto-send = N in sheet
    assert client.post("/api/outbound", json={**base, "project": "Website", "to": "priya@acme.com", "mode": "send"}).status_code == 403
    # Recipient differs from sheet stakeholder
    assert client.post("/api/outbound", json={**base, "project": "Acme rollout", "to": "other@acme.com", "mode": "send"}).status_code == 403
    assert client.post("/api/outbound", json={**base, "project": "Acme rollout", "to": "Priya@acme.com", "mode": "send"}).status_code == 200
    assert google == [("draft", "x@y.com"), ("send", "Priya@acme.com")]
    assert [r["status"] for r in client.get("/api/outbound").json()] == ["sent", "drafted"]


def test_compose_uses_writer_model(google, fake_llm):
    fake_llm["replies"] = [json.dumps({"subject": "Acme rollout: update", "body": "Hi Priya, ..."})]
    r = client.post("/api/projects/compose", json={"project": "acme rollout"})
    assert r.status_code == 200
    assert r.json() == {"to": "priya@acme.com", "subject": "Acme rollout: update", "body": "Hi Priya, ..."}


def _seed(**kw):
    db = SessionLocal()
    defaults = dict(thread_id="t", sender="A", sender_email="a@x.com", subject="s", received_at=datetime.now(timezone.utc) - timedelta(hours=1), analyzed=True, category="Customer", urgency="normal", action="fyi", summary="x")
    db.add(Email(**{**defaults, **kw}))
    db.commit()


def test_dashboard_groups_and_dismiss():
    _seed(id="1", urgency="urgent", action="reply")
    _seed(id="2", urgency="low", category="Newsletter")
    _seed(id="3", urgency="high", action="waiting", deadline="Friday")
    d = client.get("/api/dashboard").json()
    assert [e["id"] for e in d["urgent"]] == ["1", "3"]
    assert [e["id"] for e in d["needs_reply"]] == ["1"]
    assert [e["id"] for e in d["waiting"]] == ["3"] and [e["id"] for e in d["deadlines"]] == ["3"]
    assert d["by_category"] == {"Customer": 2, "Newsletter": 1}
    assert d["urgent"][0]["received_at"].endswith("+00:00")

    r = client.patch("/api/emails/1", json={"dismissed": True})
    assert r.json()["overridden"] is False
    assert [e["id"] for e in client.get("/api/dashboard").json()["urgent"]] == ["3"]
    assert client.patch("/api/emails/2", json={"urgency": "high"}).json()["overridden"] is True
