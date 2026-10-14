"""AI email triage: category, urgency (+ reason), action, deadline, summary."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.llm import ModelConfig, get_json

CATEGORIES = ["Investor", "Customer", "Hiring", "Vendor", "Legal/Finance", "Internal", "Newsletter", "Spam", "Other"]
URGENCIES = ["urgent", "high", "normal", "low"]
ACTIONS = ["reply", "review", "fyi", "waiting"]


class EmailAnalysis(BaseModel):
    category: str = Field(description=f"One of: {', '.join(CATEGORIES)}")
    urgency: Literal["urgent", "high", "normal", "low"]
    urgency_reason: str = Field(description="One short sentence explaining the urgency level")
    action: Literal["reply", "review", "fyi", "waiting"] = Field(
        description="reply = founder must respond; review = read/decide; fyi = no action; waiting = founder is waiting on someone else"
    )
    deadline: str | None = Field(None, description="Explicit or implied deadline, e.g. '2026-10-17' or 'end of week'; null if none")
    summary: str = Field(description="1-2 sentence summary of what the email is about and what is being asked")
    related_project: str | None = Field(None, description="Name of the related project from the provided list, or null")

    @field_validator("category", mode="before")
    @classmethod
    def _category(cls, v):
        match = {c.lower(): c for c in CATEGORIES}.get(str(v).strip().lower())
        return match or "Other"

    @field_validator("urgency", "action", mode="before")
    @classmethod
    def _lower(cls, v):
        return str(v).strip().lower()


SYSTEM = """You are the AI chief of staff for a startup founder. You triage the founder's inbox.
For each email decide its category, how urgent it is for the founder, what action the founder needs to take,
any deadline, and a crisp summary. Be calibrated: "urgent" means it needs attention today (deadlines today/tomorrow,
important customer escalation, investor term sheets, legal/payment issues). Most emails are "normal" or "low".
Newsletters, notifications and marketing are low urgency and fyi."""


def build_prompt(email: dict, projects: list[str]) -> str:
    project_line = ", ".join(projects) if projects else "(none)"
    return f"""Known projects: {project_line}

From: {email['sender']} <{email['sender_email']}>
To: {email['to']}
Date: {email['received_at']}
Subject: {email['subject']}

{email['body'] or email['snippet']}"""


def analyze(cfg: ModelConfig, email: dict, projects: list[str] | None = None) -> EmailAnalysis:
    """Classify one email. Bulk mail (List-Unsubscribe) skips the LLM to save cost."""
    if email.get("is_bulk"):
        return EmailAnalysis(
            category="Newsletter",
            urgency="low",
            urgency_reason="Bulk/mailing-list email",
            action="fyi",
            summary=email.get("snippet") or email.get("subject", ""),
        )
    return get_json(cfg, SYSTEM, build_prompt(email, projects or []), EmailAnalysis)
