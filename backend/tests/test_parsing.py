import base64

from app.google_client import parse_message, parse_sheet_id
from app.projects import find_project, parse_rows


def b64(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")


def test_parse_multipart_message_prefers_plain_text():
    msg = {
        "id": "m1",
        "threadId": "t1",
        "internalDate": "1760400000000",
        "snippet": "Hi &amp; hello",
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": [
                {"name": "From", "value": "Priya Shah <Priya@Acme.com>"},
                {"name": "Subject", "value": "Q4 plan"},
                {"name": "List-Unsubscribe", "value": "<mailto:x>"},
            ],
            "parts": [
                {"mimeType": "text/plain", "body": {"data": b64("plain body")}},
                {"mimeType": "text/html", "body": {"data": b64("<p>html body</p>")}},
            ],
        },
    }
    out = parse_message(msg)
    assert out["sender"] == "Priya Shah" and out["sender_email"] == "priya@acme.com"
    assert out["body"] == "plain body"
    assert out["snippet"] == "Hi & hello"
    assert out["is_bulk"] is True


def test_parse_html_only_message():
    msg = {"id": "m2", "payload": {"mimeType": "text/html", "headers": [], "body": {"data": b64("<div>Hello<br>world</div><style>x{}</style>")}}}
    assert parse_message(msg)["body"] == "Hello\nworld"


def test_parse_sheet_id():
    url = "https://docs.google.com/spreadsheets/d/1AbC-d_9/edit#gid=0"
    assert parse_sheet_id(url) == "1AbC-d_9"
    assert parse_sheet_id(" 1AbC-d_9 ") == "1AbC-d_9"


def test_parse_rows_normalizes_headers_and_auto_send():
    values = [
        ["Project", "Status", "Recent updates", "Stakeholder Name", "Stakeholder Email", "Auto-send"],
        ["Acme rollout", "At risk", "SSO delayed", "Priya", "priya@acme.com", "Y"],
        ["", "ignored row"],
        ["Website", "On track"],
    ]
    rows = parse_rows(values)
    assert [r["project"] for r in rows] == ["Acme rollout", "Website"]
    assert rows[0]["updates"] == "SSO delayed" and rows[0]["auto_send"] is True
    assert rows[1]["auto_send"] is False and rows[1]["stakeholder_email"] == ""
    assert find_project(rows, "acme ROLLOUT ")["status"] == "At risk"
