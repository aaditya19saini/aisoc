"""Helpers for the key/value settings table."""

from sqlalchemy.orm import Session

from app.config import decrypt, encrypt
from app.models import Setting


def get_setting(db: Session, key: str, default: str = "") -> str:
    row = db.get(Setting, key)
    if row is None or row.value == "":
        return default
    return decrypt(row.value) if row.encrypted else row.value


def set_setting(db: Session, key: str, value: str, secret: bool = False) -> None:
    row = db.get(Setting, key) or Setting(key=key)
    row.value = encrypt(value) if (secret and value) else value
    row.encrypted = secret and bool(value)
    db.add(row)
    db.commit()


def delete_setting(db: Session, key: str) -> None:
    row = db.get(Setting, key)
    if row is not None:
        db.delete(row)
        db.commit()
