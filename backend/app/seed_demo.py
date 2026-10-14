"""Seed a few already-classified demo emails so the dashboard can be previewed without Gmail.

Usage: uv run python -m app.seed_demo   (remove with: uv run python -m app.seed_demo --clear)
"""

import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete

from app.db import SessionLocal, init_db
from app.models import Email
from app.store import set_setting

NOW = datetime.now(timezone.utc)

DEMO = [
    ("Priya Shah", "priya@acme.com", "MSA needs your signature today", "Customer", "urgent", "Contract signature due by 5pm today; launch slips otherwise.", "reply", "Today 5pm", "Acme needs the signed MSA today to keep the Nov 1 launch.", "Acme rollout", 2),
    ("Rahul Mehta", "rahul@sequoia.example", "Follow-up on our seed conversation", "Investor", "high", "Investor asking for the data room before Friday's partner meeting.", "reply", "Friday", "Wants data room access and updated metrics before the partner meeting.", None, 5),
    ("Ankit (CTO)", "ankit@startup.example", "SSO integration blocked on Okta", "Internal", "high", "Blocker on a customer-committed feature.", "review", None, "Okta sandbox access is blocking SSO; needs a decision on a workaround.", "Acme rollout", 9),
    ("Neha", "neha@talentco.example", "Senior backend candidate: offer?", "Hiring", "normal", "Candidate has a competing offer; decision needed this week.", "reply", "This week", "Recruiter asks whether to extend an offer to the senior backend candidate.", None, 20),
    ("AWS Billing", "billing@aws.example", "Your invoice is available", "Legal/Finance", "low", "Routine invoice, auto-paid.", "fyi", None, "October AWS invoice of $4,212 is available.", None, 30),
    ("Vikram", "vikram@designstudio.example", "Re: landing page revisions", "Vendor", "normal", "Vendor waiting is fine; ball is in their court.", "waiting", None, "You asked for v3 of the landing page; they promised it Monday.", "Website", 40),
    ("Product Hunt", "hello@producthunt.example", "Top launches this week", "Newsletter", "low", "Bulk/mailing-list email", "fyi", None, "Weekly digest of top launches.", None, 50),
]


def main() -> None:
    init_db()
    db = SessionLocal()
    db.execute(delete(Email).where(Email.id.like("demo-%")))
    if "--clear" not in sys.argv:
        for i, (sender, addr, subject, cat, urg, reason, action, deadline, summary, project, hours) in enumerate(DEMO):
            db.add(Email(
                id=f"demo-{i}", thread_id=f"demo-{i}", sender=sender, sender_email=addr, subject=subject, snippet=summary,
                received_at=NOW - timedelta(hours=hours), analyzed=True, category=cat, urgency=urg, urgency_reason=reason,
                action=action, deadline=deadline, summary=summary, related_project=project, analysis_model="demo",
            ))
        set_setting(db, "digest.text", "Two things need you today: Priya at Acme needs the signed MSA by 5pm or the Nov 1 launch slips, and Rahul wants data room access before Friday's partner meeting. Ankit is blocked on Okta for SSO, which also puts Acme at risk, so a quick call with him would help. Neha needs an offer decision on the backend candidate this week.")
        set_setting(db, "digest.at", NOW.isoformat())
    db.commit()
    print("cleared demo data" if "--clear" in sys.argv else f"seeded {len(DEMO)} demo emails")


if __name__ == "__main__":
    main()
