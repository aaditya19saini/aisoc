import os
from pathlib import Path

from cryptography.fernet import Fernet
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    database_url: str = f"sqlite:///{BACKEND_DIR / 'aicos.db'}"
    secret_key: str = ""  # Fernet key; auto-generated into .secret_key if empty
    google_client_secrets_file: str = str(BACKEND_DIR / "credentials.json")
    google_redirect_uri: str = "http://localhost:8000/auth/google/callback"
    frontend_url: str = "http://localhost:3000"
    sync_days: int = 14
    sync_max_emails: int = 100


settings = Settings()

# Local OAuth over http://localhost; Google may also return scopes in a different order.
os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")


def _load_fernet() -> Fernet:
    if settings.secret_key:
        return Fernet(settings.secret_key.encode())
    key_file = BACKEND_DIR / ".secret_key"
    if not key_file.exists():
        key_file.write_bytes(Fernet.generate_key())
        key_file.chmod(0o600)
    return Fernet(key_file.read_bytes().strip())


fernet = _load_fernet()


def encrypt(value: str) -> str:
    return fernet.encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    return fernet.decrypt(value.encode()).decode()
