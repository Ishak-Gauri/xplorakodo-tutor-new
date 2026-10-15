"""Settings read from environment variables (and a .env file when python-dotenv is installed).

Runtime knobs that an admin can change from the console (kill switch, budget, router weights)
live in the `settings` table instead; see app/settings_store.py.
"""
import os
import secrets
import sys
from dataclasses import dataclass

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # dotenv is optional
    pass


@dataclass(frozen=True)
class Settings:
    database_url: str
    jwt_secret: str
    jwt_hours: int
    admin_email: str
    admin_password: str
    admin_name: str
    llm_provider: str            # mock | anthropic | openai
    anthropic_model: str
    openai_model: str
    embedding_provider: str      # hash | openai
    public_base_url: str
    seed_demo: bool


def _jwt_secret() -> str:
    value = os.getenv("JWT_SECRET", "")
    if value:
        return value
    # Fine for local runs; on a server set JWT_SECRET so logins survive restarts.
    print("[config] JWT_SECRET not set: using a random one (logins reset on restart).", file=sys.stderr)
    return secrets.token_urlsafe(48)


def get_settings() -> Settings:
    return Settings(
        database_url=os.getenv("DATABASE_URL", "postgresql://xk:xk@localhost:5432/xplorakodo"),
        jwt_secret=_jwt_secret(),
        jwt_hours=int(os.getenv("JWT_HOURS", "12")),
        admin_email=os.getenv("ADMIN_EMAIL", "admin@xplorakodo.com").strip().lower(),
        admin_password=os.getenv("ADMIN_PASSWORD", "ChangeMe!2026"),
        admin_name=os.getenv("ADMIN_NAME", "Platform Admin"),
        llm_provider=os.getenv("LLM_PROVIDER", "openai").lower(),  # falls back to mock without a key
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-haiku-5-5"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),  # any chat model with JSON mode
        embedding_provider=os.getenv("EMBEDDING_PROVIDER", "hash").lower(),
        public_base_url=os.getenv("PUBLIC_BASE_URL", "").rstrip("/"),
        seed_demo=os.getenv("SEED_DEMO", "true").lower() in ("1", "true", "yes"),
    )
