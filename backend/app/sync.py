"""Inbox sync + classification + daily digest."""

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import classifier, composer, google_client, projects
from app.llm import LLMError, get_model_config
from app.models import Email
from app.store import set_setting

log = logging.getLogger(__name__)

URGENCY_RANK = {"urgent": 0, "high": 1, "normal": 2, "low": 3}


def email_to_dict(e: Email) -> dict:
    return {c.name: getattr(e, c.name) for c in Email.__table__.columns if c.name != "body"}


def sync_inbox(db: Session, days: int, max_emails: int) -> dict:
    ids = google_client.list_inbox_ids(db, days, max_emails)
    existing = set(db.scalars(select(Email.id).where(Email.id.in_(ids)))) if ids else set()
    new_ids = [i for i in ids if i not in existing]
    for data in google_client.fetch_messages(db, new_ids):
        db.add(Email(**data))
    db.commit()

    result = {"fetched": len(new_ids), **classify_pending(db)}
    if result["classified"]:
        result["digest_error"] = refresh_digest(db)
    set_setting(db, "sync.last_at", datetime.now(timezone.utc).isoformat())
    return result


def classify_pending(db: Session, limit: int = 200) -> dict:
    cfg = get_model_config(db, "classifier")
    try:
        project_names = [p["project"] for p in projects.load_projects(db)]
    except Exception as e:  # sheet not configured / not shared: classify without project hints
        log.warning("could not load projects for classification: %s", e)
        project_names = []

    pending = list(db.scalars(select(Email).where(Email.analyzed.is_(False)).order_by(Email.received_at.desc()).limit(limit)))
    if not pending:
        return {"classified": 0, "errors": []}

    def run(e: Email):
        data = {**email_to_dict(e), "body": e.body}
        try:
            return e, classifier.analyze(cfg, data, project_names), None
        except LLMError as err:
            return e, None, str(err)

    errors = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        for e, analysis, err in pool.map(run, pending):
            if err:
                e.analysis_error = err
                errors.append(f"{e.subject[:60]}: {err}")
                continue
            for field, value in analysis.model_dump().items():
                setattr(e, field, value)
            e.analyzed = True
            e.analysis_error = None
            e.analysis_model = cfg.litellm_model if not e.is_bulk else "rule:bulk"
    db.commit()
    return {"classified": len(pending) - len(errors), "errors": errors[:10]}


def attention_emails(db: Session, days: int = 3) -> list[Email]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = db.scalars(
        select(Email).where(
            Email.analyzed.is_(True),
            Email.dismissed.is_(False),
            Email.received_at >= since,
            (Email.urgency.in_(["urgent", "high"])) | (Email.action.in_(["reply", "review"])) | (Email.deadline.is_not(None)),
        )
    )
    return sorted(rows, key=lambda e: (URGENCY_RANK.get(e.urgency or "", 9), -e.received_at.timestamp()))[:30]


def refresh_digest(db: Session) -> str | None:
    """Regenerate the dashboard narrative. Returns an error string instead of raising."""
    try:
        text = composer.write_digest(get_model_config(db, "writer"), [email_to_dict(e) for e in attention_emails(db)])
    except LLMError as e:
        return str(e)
    set_setting(db, "digest.text", text)
    set_setting(db, "digest.at", datetime.now(timezone.utc).isoformat())
    return None
