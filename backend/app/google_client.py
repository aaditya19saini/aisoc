"""Google OAuth, Gmail (sync / draft / send) and Sheets access."""

import base64
import json
import re
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import parseaddr
from html import unescape

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from sqlalchemy.orm import Session

from app.config import settings
from app.store import delete_setting, get_setting, set_setting

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/spreadsheets.readonly",
]
TOKEN_KEY = "google.token"
BODY_MAX_CHARS = 8000

_pending_verifiers: dict[str, str] = {}  # OAuth state -> PKCE code verifier (single-user, in memory)


class GoogleNotConnected(Exception):
    pass


# ---------- OAuth ----------

def _flow(**kwargs) -> Flow:
    return Flow.from_client_secrets_file(
        settings.google_client_secrets_file, scopes=SCOPES, redirect_uri=settings.google_redirect_uri, **kwargs
    )


def auth_url() -> str:
    flow = _flow()
    url, state = flow.authorization_url(access_type="offline", prompt="consent", include_granted_scopes="true")
    _pending_verifiers[state] = flow.code_verifier
    return url


def finish_auth(db: Session, state: str, code: str) -> None:
    verifier = _pending_verifiers.pop(state, None)
    if verifier is None:
        raise ValueError("unknown or expired OAuth state; start the connection again")
    flow = _flow(state=state, code_verifier=verifier)
    flow.fetch_token(code=code)
    _save_credentials(db, flow.credentials)
    set_setting(db, "google.email", gmail_service(db).users().getProfile(userId="me").execute()["emailAddress"])


def disconnect(db: Session) -> None:
    delete_setting(db, TOKEN_KEY)
    delete_setting(db, "google.email")


def is_connected(db: Session) -> bool:
    return bool(get_setting(db, TOKEN_KEY))


def _save_credentials(db: Session, creds: Credentials) -> None:
    set_setting(db, TOKEN_KEY, creds.to_json(), secret=True)


def get_credentials(db: Session) -> Credentials:
    raw = get_setting(db, TOKEN_KEY)
    if not raw:
        raise GoogleNotConnected("Google account not connected")
    creds = Credentials.from_authorized_user_info(json.loads(raw), SCOPES)
    if not creds.valid and creds.refresh_token:
        creds.refresh(Request())
        _save_credentials(db, creds)
    return creds


def gmail_service(db: Session):
    return build("gmail", "v1", credentials=get_credentials(db), cache_discovery=False)


def sheets_service(db: Session):
    return build("sheets", "v4", credentials=get_credentials(db), cache_discovery=False)


# ---------- Gmail read ----------

def list_inbox_ids(db: Session, days: int, max_results: int) -> list[str]:
    svc = gmail_service(db)
    ids: list[str] = []
    page_token = None
    while len(ids) < max_results:
        resp = (
            svc.users()
            .messages()
            .list(userId="me", q=f"in:inbox newer_than:{days}d", maxResults=min(100, max_results - len(ids)), pageToken=page_token)
            .execute()
        )
        ids += [m["id"] for m in resp.get("messages", [])]
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return ids


def fetch_messages(db: Session, message_ids: list[str]) -> list[dict]:
    svc = gmail_service(db)
    return [parse_message(svc.users().messages().get(userId="me", id=mid, format="full").execute()) for mid in message_ids]


def parse_message(msg: dict) -> dict:
    """Turn a Gmail API message into the fields we store."""
    payload = msg.get("payload", {})
    headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
    name, addr = parseaddr(headers.get("from", ""))
    return {
        "id": msg["id"],
        "thread_id": msg.get("threadId", msg["id"]),
        "sender": name or addr,
        "sender_email": addr.lower(),
        "to": headers.get("to", ""),
        "subject": headers.get("subject", "(no subject)"),
        "snippet": unescape(msg.get("snippet", "")),
        "body": _extract_body(payload)[:BODY_MAX_CHARS],
        "received_at": datetime.fromtimestamp(int(msg.get("internalDate", "0")) / 1000, tz=timezone.utc),
        "is_bulk": "list-unsubscribe" in headers,
    }


def _extract_body(payload: dict) -> str:
    plain, html = [], []

    def walk(part: dict) -> None:
        mime = part.get("mimeType", "")
        data = part.get("body", {}).get("data")
        if data and mime == "text/plain":
            plain.append(_b64decode(data))
        elif data and mime == "text/html":
            html.append(_b64decode(data))
        for sub in part.get("parts", []) or []:
            walk(sub)

    walk(payload)
    if plain:
        return "\n".join(plain).strip()
    return _html_to_text("\n".join(html))


def _b64decode(data: str) -> str:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")


def _html_to_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    html = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>", "\n", html)
    text = unescape(re.sub(r"<[^>]+>", " ", html))
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n\n", text)).strip()


# ---------- Gmail write ----------

def _raw_message(to: str, subject: str, body: str) -> str:
    msg = EmailMessage()
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


def create_draft(db: Session, to: str, subject: str, body: str) -> str:
    draft = (
        gmail_service(db).users().drafts()
        .create(userId="me", body={"message": {"raw": _raw_message(to, subject, body)}})
        .execute()
    )
    return draft["id"]


def send_email(db: Session, to: str, subject: str, body: str) -> str:
    sent = gmail_service(db).users().messages().send(userId="me", body={"raw": _raw_message(to, subject, body)}).execute()
    return sent["id"]


# ---------- Sheets ----------

def parse_sheet_id(value: str) -> str:
    """Accept a full Google Sheets URL or a bare spreadsheet id."""
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", value)
    return m.group(1) if m else value.strip()


def read_sheet(db: Session, sheet_id: str, range_: str) -> list[list[str]]:
    resp = sheets_service(db).spreadsheets().values().get(spreadsheetId=sheet_id, range=range_).execute()
    return resp.get("values", [])
