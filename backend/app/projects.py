"""Project rows from the Google Sheet."""

import re

from sqlalchemy.orm import Session

from app import google_client
from app.store import get_setting

# Header aliases -> canonical keys
ALIASES = {
    "project_name": "project",
    "name": "project",
    "recent_updates": "updates",
    "update": "updates",
    "next_step": "next_steps",
    "blocker": "blockers",
    "progress_percent": "progress",
    "stakeholder": "stakeholder_name",
    "email": "stakeholder_email",
    "stakeholder_mail": "stakeholder_email",
    "autosend": "auto_send",
}
TRUTHY = {"y", "yes", "true", "1"}


def normalize_header(h: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "_", h.strip().lower()).strip("_")
    return ALIASES.get(key, key)


def parse_rows(values: list[list[str]]) -> list[dict]:
    """First row = headers. Returns one dict per non-empty project row."""
    if not values:
        return []
    headers = [normalize_header(h) for h in values[0]]
    rows = []
    for raw in values[1:]:
        row = {h: (raw[i].strip() if i < len(raw) else "") for i, h in enumerate(headers) if h}
        if not row.get("project"):
            continue
        row["auto_send"] = row.get("auto_send", "").lower() in TRUTHY
        rows.append(row)
    return rows


def load_projects(db: Session) -> list[dict]:
    sheet_id = get_setting(db, "sheet.id")
    if not sheet_id:
        return []
    return parse_rows(google_client.read_sheet(db, sheet_id, get_setting(db, "sheet.range", "A1:Z200")))


def find_project(projects: list[dict], name: str) -> dict | None:
    return next((p for p in projects if p["project"].lower() == name.strip().lower()), None)
