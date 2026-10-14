import json
from datetime import datetime, timezone

from app import classifier
from app.llm import ModelConfig

EMAIL = {
    "sender": "Priya",
    "sender_email": "priya@acme.com",
    "to": "me@startup.com",
    "subject": "Contract needs signature today",
    "snippet": "",
    "body": "Hi, legal needs the signed MSA by 5pm today or we slip the launch.",
    "received_at": datetime(2026, 10, 14, tzinfo=timezone.utc),
    "is_bulk": False,
}


def test_analyze_parses_and_normalizes(fake_llm):
    fake_llm["replies"] = [
        json.dumps(
            {
                "category": "customer",
                "urgency": "URGENT",
                "urgency_reason": "Signature due today",
                "action": "Reply",
                "deadline": "2026-10-14 17:00",
                "summary": "Acme needs the signed MSA today.",
                "related_project": "Acme rollout",
            }
        )
    ]
    a = classifier.analyze(ModelConfig("anthropic", "claude-haiku-5-5"), EMAIL, ["Acme rollout"])
    assert (a.category, a.urgency, a.action) == ("Customer", "urgent", "reply")
    assert a.related_project == "Acme rollout"


def test_unknown_category_maps_to_other(fake_llm):
    fake_llm["replies"] = ['{"category":"Party","urgency":"low","urgency_reason":"-","action":"fyi","summary":"x"}']
    assert classifier.analyze(ModelConfig("openai", "m"), EMAIL).category == "Other"


def test_bulk_mail_skips_llm(fake_llm):
    a = classifier.analyze(ModelConfig("openai", "m"), {**EMAIL, "is_bulk": True, "snippet": "Weekly digest"})
    assert a.category == "Newsletter" and a.urgency == "low"
    assert fake_llm["models"] == []
