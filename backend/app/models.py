from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Setting(Base):
    """Key/value store for model config, Google token, sheet id, cached digest."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    encrypted: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Email(Base):
    __tablename__ = "emails"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # Gmail message id
    thread_id: Mapped[str] = mapped_column(String, index=True)
    sender: Mapped[str] = mapped_column(String, default="")
    sender_email: Mapped[str] = mapped_column(String, default="", index=True)
    to: Mapped[str] = mapped_column(Text, default="")
    subject: Mapped[str] = mapped_column(Text, default="")
    snippet: Mapped[str] = mapped_column(Text, default="")
    body: Mapped[str] = mapped_column(Text, default="")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    is_bulk: Mapped[bool] = mapped_column(Boolean, default=False)  # has List-Unsubscribe

    # AI analysis
    analyzed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    category: Mapped[str | None] = mapped_column(String, index=True)
    urgency: Mapped[str | None] = mapped_column(String, index=True)
    urgency_reason: Mapped[str | None] = mapped_column(Text)
    action: Mapped[str | None] = mapped_column(String, index=True)
    deadline: Mapped[str | None] = mapped_column(String)
    summary: Mapped[str | None] = mapped_column(Text)
    related_project: Mapped[str | None] = mapped_column(String)
    analysis_model: Mapped[str | None] = mapped_column(String)
    analysis_error: Mapped[str | None] = mapped_column(Text)
    overridden: Mapped[bool] = mapped_column(Boolean, default=False)
    dismissed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)  # marked done on the dashboard


class Outbound(Base):
    """Log of every AI-generated email saved as a draft or sent."""

    __tablename__ = "outbound"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project: Mapped[str] = mapped_column(String, default="")
    to: Mapped[str] = mapped_column(String)
    subject: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(String)  # draft | send
    status: Mapped[str] = mapped_column(String)  # drafted | sent | failed
    gmail_id: Mapped[str | None] = mapped_column(String)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
