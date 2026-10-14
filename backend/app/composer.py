"""AI writer: project status emails and the dashboard's daily story."""

from pydantic import BaseModel

from app.llm import ModelConfig, get_json, get_text


class DraftEmail(BaseModel):
    subject: str
    body: str


COMPOSE_SYSTEM = """You are the AI chief of staff for a startup founder. You write project status update emails
on the founder's behalf to the project's stakeholder. Be concise, specific and honest about risks and blockers.
Adapt tone to the recipient's role (investors: high-level and metric-focused; clients: outcome-focused and reassuring;
teammates: direct and action-oriented). Plain text, no markdown. Sign off as the founder without inventing a name;
end with "Best," on its own line. Never invent facts that are not in the project data."""


def compose_status_email(cfg: ModelConfig, project: dict, related: list[dict], instructions: str = "") -> DraftEmail:
    fields = "\n".join(f"- {k.replace('_', ' ').title()}: {v}" for k, v in project.items() if v not in ("", None) and k != "auto_send")
    related_txt = "\n".join(f"- {e['received_at']:%Y-%m-%d} from {e['sender']}: {e['summary']}" for e in related) or "(none)"
    prompt = f"""Project data:
{fields}

Recent related emails:
{related_txt}

Extra instructions from the founder: {instructions or '(none)'}

Write the status update email to {project.get('stakeholder_name') or 'the stakeholder'}."""
    return get_json(cfg, COMPOSE_SYSTEM, prompt, DraftEmail)


DIGEST_SYSTEM = """You are the AI chief of staff for a startup founder. Write a short morning briefing (3-5 sentences,
plain text, no lists, no markdown) telling the founder what matters in their inbox: what needs them today, who is
waiting on a reply, and any deadlines or risks. Mention people/companies by name. If nothing is pressing, say so."""


def write_digest(cfg: ModelConfig, emails: list[dict]) -> str:
    if not emails:
        return "Nothing pressing in your inbox right now."
    lines = "\n".join(
        f"- [{e['urgency']}/{e['action']}] {e['category']} | {e['sender']} | {e['subject']} | {e['summary']}"
        + (f" | deadline: {e['deadline']}" if e.get("deadline") else "")
        for e in emails
    )
    return get_text(cfg, DIGEST_SYSTEM, f"Emails from the last few days needing attention:\n{lines}", max_tokens=600).strip()
