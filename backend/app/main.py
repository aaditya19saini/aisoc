import os
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import composer, google_client, llm, projects
from app.config import settings
from app.db import get_db, init_db
from app.models import Email, Outbound
from app.store import get_setting, set_setting
from app.sync import URGENCY_RANK, classify_pending, email_to_dict, refresh_digest, sync_inbox

app = FastAPI(title="AI Chief of Staff")
init_db()


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).isoformat()


def serialize(e: Email) -> dict:
    d = email_to_dict(e)
    d["received_at"] = _iso(e.received_at)
    return d


def require_google(db: Session) -> None:
    if not google_client.is_connected(db):
        raise HTTPException(400, "Connect your Google account in Settings first.")


@app.get("/api/health")
def health():
    return {"ok": True}


# ---------- Settings ----------

class ModelSettingsIn(BaseModel):
    provider: str
    model: str
    api_key: str | None = None  # None = keep existing key, "" = clear it
    api_base: str | None = None


class SheetIn(BaseModel):
    sheet: str
    range: str = "A1:Z200"


@app.get("/api/settings")
def get_settings(db: Session = Depends(get_db)):
    models = {}
    for task in llm.TASKS:
        cfg = llm.get_model_config(db, task)
        models[task] = {
            "provider": cfg.provider,
            "model": cfg.model,
            "api_base": cfg.api_base or "",
            "has_key": bool(cfg.api_key),
            "key_hint": f"…{cfg.api_key[-4:]}" if cfg.api_key else "",
        }
    return {
        "providers": llm.PROVIDERS,
        "models": models,
        "google": {
            "connected": google_client.is_connected(db),
            "email": get_setting(db, "google.email"),
            "credentials_file_present": os.path.exists(settings.google_client_secrets_file),
        },
        "sheet": {"id": get_setting(db, "sheet.id"), "range": get_setting(db, "sheet.range", "A1:Z200")},
    }


@app.put("/api/settings/models/{task}")
def save_model_settings(task: str, body: ModelSettingsIn, db: Session = Depends(get_db)):
    if task not in llm.TASKS:
        raise HTTPException(404, "unknown task")
    if body.provider not in llm.PROVIDERS:
        raise HTTPException(400, f"unknown provider {body.provider!r}")
    set_setting(db, f"llm.{task}.provider", body.provider)
    set_setting(db, f"llm.{task}.model", body.model.strip())
    set_setting(db, f"llm.{task}.api_base", (body.api_base or "").strip())
    if body.api_key is not None:
        set_setting(db, f"llm.{task}.api_key", body.api_key.strip(), secret=True)
    return get_settings(db)


@app.post("/api/settings/models/{task}/test")
def test_model(task: str, db: Session = Depends(get_db)):
    if task not in llm.TASKS:
        raise HTTPException(404, "unknown task")
    cfg = llm.get_model_config(db, task)
    try:
        reply = llm.get_text(cfg, "You are a connection test.", "Reply with exactly: OK", max_tokens=10)
    except llm.LLMError as e:
        return {"ok": False, "model": cfg.litellm_model, "error": str(e)}
    return {"ok": True, "model": cfg.litellm_model, "reply": reply.strip()}


@app.put("/api/settings/sheet")
def save_sheet(body: SheetIn, db: Session = Depends(get_db)):
    set_setting(db, "sheet.id", google_client.parse_sheet_id(body.sheet) if body.sheet.strip() else "")
    set_setting(db, "sheet.range", body.range.strip() or "A1:Z200")
    return get_settings(db)


# ---------- Google OAuth ----------

@app.get("/auth/google/start")
def google_start():
    try:
        return RedirectResponse(google_client.auth_url())
    except FileNotFoundError:
        raise HTTPException(500, f"Google OAuth client file not found at {settings.google_client_secrets_file}")


@app.get("/auth/google/callback")
def google_callback(state: str, code: str | None = None, error: str | None = None, db: Session = Depends(get_db)):
    if error or not code:
        return RedirectResponse(f"{settings.frontend_url}/settings?google=error&reason={error or 'no_code'}")
    try:
        google_client.finish_auth(db, state, code)
    except Exception as e:
        return RedirectResponse(f"{settings.frontend_url}/settings?google=error&reason={type(e).__name__}")
    return RedirectResponse(f"{settings.frontend_url}/settings?google=connected")


@app.post("/api/google/disconnect")
def google_disconnect(db: Session = Depends(get_db)):
    google_client.disconnect(db)
    return {"ok": True}


# ---------- Inbox ----------

class SyncIn(BaseModel):
    days: int | None = None


@app.post("/api/sync")
def sync(body: SyncIn | None = None, db: Session = Depends(get_db)):
    require_google(db)
    days = (body.days if body and body.days else None) or settings.sync_days
    return sync_inbox(db, days, settings.sync_max_emails)


@app.post("/api/classify")
def classify(db: Session = Depends(get_db)):
    """Retry classification of emails that failed (e.g. after fixing the model/API key)."""
    return classify_pending(db)


@app.get("/api/emails")
def list_emails(
    category: str | None = None,
    urgency: str | None = None,
    action: str | None = None,
    q: str | None = None,
    include_dismissed: bool = False,
    limit: int = 200,
    db: Session = Depends(get_db),
):
    stmt = select(Email).order_by(Email.received_at.desc()).limit(min(limit, 500))
    if category:
        stmt = stmt.where(Email.category == category)
    if urgency:
        stmt = stmt.where(Email.urgency == urgency)
    if action:
        stmt = stmt.where(Email.action == action)
    if not include_dismissed:
        stmt = stmt.where(Email.dismissed.is_(False))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(Email.subject.ilike(like) | Email.sender.ilike(like) | Email.summary.ilike(like))
    return [serialize(e) for e in db.scalars(stmt)]


class EmailPatch(BaseModel):
    category: str | None = None
    urgency: str | None = None
    action: str | None = None
    dismissed: bool | None = None


@app.patch("/api/emails/{email_id}")
def update_email(email_id: str, body: EmailPatch, db: Session = Depends(get_db)):
    e = db.get(Email, email_id)
    if e is None:
        raise HTTPException(404, "email not found")
    changes = body.model_dump(exclude_none=True)
    for field, value in changes.items():
        setattr(e, field, value)
    if set(changes) - {"dismissed"}:
        e.overridden = True  # human correction; kept for future prompt tuning
    db.commit()
    return serialize(e)


# ---------- Dashboard ----------

@app.get("/api/dashboard")
def dashboard(db: Session = Depends(get_db)):
    since = datetime.now(timezone.utc) - timedelta(days=settings.sync_days)
    base = select(Email).where(Email.analyzed.is_(True), Email.dismissed.is_(False), Email.received_at >= since)
    emails = list(db.scalars(base.order_by(Email.received_at.desc())))

    def counts(col):
        rows = db.execute(
            select(col, func.count()).where(Email.analyzed.is_(True), Email.received_at >= since).group_by(col)
        ).all()
        return {k: n for k, n in rows if k}

    by_urgency = lambda es: sorted(es, key=lambda e: (URGENCY_RANK.get(e.urgency or "", 9), -e.received_at.timestamp()))
    return {
        "digest": {"text": get_setting(db, "digest.text"), "at": get_setting(db, "digest.at")},
        "last_sync": get_setting(db, "sync.last_at"),
        "totals": {
            "emails": db.scalar(select(func.count()).select_from(Email).where(Email.received_at >= since)),
            "unclassified": db.scalar(select(func.count()).select_from(Email).where(Email.analyzed.is_(False))),
            "urgent": sum(e.urgency == "urgent" for e in emails),
            "needs_reply": sum(e.action == "reply" for e in emails),
        },
        "by_category": counts(Email.category),
        "by_urgency": counts(Email.urgency),
        "urgent": [serialize(e) for e in by_urgency([e for e in emails if e.urgency in ("urgent", "high")])[:15]],
        "needs_reply": [serialize(e) for e in by_urgency([e for e in emails if e.action == "reply"])[:15]],
        "waiting": [serialize(e) for e in emails if e.action == "waiting"][:15],
        "deadlines": [serialize(e) for e in by_urgency([e for e in emails if e.deadline])[:15]],
    }


@app.post("/api/dashboard/digest")
def regenerate_digest(db: Session = Depends(get_db)):
    err = refresh_digest(db)
    if err:
        raise HTTPException(502, err)
    return {"text": get_setting(db, "digest.text"), "at": get_setting(db, "digest.at")}


# ---------- Projects + outbound emails ----------

class ComposeIn(BaseModel):
    project: str
    instructions: str = ""


class OutboundIn(BaseModel):
    project: str
    to: str
    subject: str
    body: str
    mode: str  # "draft" | "send"


def _load_projects_or_400(db: Session) -> list[dict]:
    require_google(db)
    if not get_setting(db, "sheet.id"):
        raise HTTPException(400, "Add your project Google Sheet in Settings first.")
    try:
        return projects.load_projects(db)
    except Exception as e:
        raise HTTPException(502, f"Could not read the Google Sheet: {e}")


@app.get("/api/projects")
def list_projects(db: Session = Depends(get_db)):
    return _load_projects_or_400(db)


@app.post("/api/projects/compose")
def compose(body: ComposeIn, db: Session = Depends(get_db)):
    project = projects.find_project(_load_projects_or_400(db), body.project)
    if project is None:
        raise HTTPException(404, "project not found in sheet")
    related = db.scalars(
        select(Email)
        .where(func.lower(Email.related_project) == project["project"].lower())
        .order_by(Email.received_at.desc())
        .limit(5)
    )
    try:
        draft = composer.compose_status_email(
            llm.get_model_config(db, "writer"), project, [email_to_dict(e) for e in related], body.instructions
        )
    except llm.LLMError as e:
        raise HTTPException(502, str(e))
    return {"to": project.get("stakeholder_email", ""), **draft.model_dump()}


@app.post("/api/outbound")
def create_outbound(body: OutboundIn, db: Session = Depends(get_db)):
    if body.mode not in ("draft", "send"):
        raise HTTPException(400, "mode must be 'draft' or 'send'")
    if not body.to.strip():
        raise HTTPException(400, "recipient is required")
    if body.mode == "send":
        # Guardrail: only send when the sheet allows it, and only to the stakeholder listed there.
        project = projects.find_project(_load_projects_or_400(db), body.project)
        if project is None or not project["auto_send"]:
            raise HTTPException(403, "Sending is disabled for this project (set Auto-send = Y in the sheet). Save as draft instead.")
        if body.to.strip().lower() != project.get("stakeholder_email", "").strip().lower():
            raise HTTPException(403, "Can only send to the stakeholder email listed in the sheet. Save as draft instead.")
    require_google(db)

    record = Outbound(project=body.project, to=body.to.strip(), subject=body.subject, body=body.body, mode=body.mode, status="failed")
    try:
        if body.mode == "draft":
            record.gmail_id = google_client.create_draft(db, record.to, record.subject, record.body)
            record.status = "drafted"
        else:
            record.gmail_id = google_client.send_email(db, record.to, record.subject, record.body)
            record.status = "sent"
    except Exception as e:
        record.error = str(e)
    db.add(record)
    db.commit()
    if record.status == "failed":
        raise HTTPException(502, f"Gmail error: {record.error}")
    return {"id": record.id, "status": record.status, "gmail_id": record.gmail_id}


@app.get("/api/outbound")
def list_outbound(db: Session = Depends(get_db)):
    rows = db.scalars(select(Outbound).order_by(Outbound.created_at.desc()).limit(100))
    return [
        {c.name: (_iso(getattr(r, c.name)) if c.name == "created_at" else getattr(r, c.name)) for c in Outbound.__table__.columns}
        for r in rows
    ]
