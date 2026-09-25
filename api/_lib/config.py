"""Server-side settings. Values come from the environment; locally also from .env.local / .env."""

import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

_ROOT = Path(__file__).resolve().parents[2]


def _load_local_env() -> None:
    # Vercel injects env vars itself; only read dotenv files for local dev and scripts.
    if os.environ.get("VERCEL"):
        return
    from dotenv import load_dotenv

    for name in (".env.local", ".env"):
        load_dotenv(_ROOT / name, override=False)


class Settings(BaseModel):
    supabase_url: str
    supabase_jwks_url: str
    database_url: str
    supabase_service_role_key: str = ""
    gemini_api_key: str = ""
    gemini_chat_model: str = "gemini-2.5-flash"
    gemini_fallback_model: str = "gemini-2.5-flash-lite"
    discord_webhook_url: str = ""

    @property
    def jwt_issuer(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/auth/v1"


@lru_cache
def get_settings() -> Settings:
    _load_local_env()
    return Settings(
        supabase_url=os.environ["NEXT_PUBLIC_SUPABASE_URL"],
        supabase_jwks_url=os.environ["SUPABASE_JWKS_URL"],
        database_url=os.environ["DATABASE_URL"],
        supabase_service_role_key=os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""),
        gemini_api_key=os.environ.get("GEMINI_API_KEY", ""),
        gemini_chat_model=os.environ.get("GEMINI_CHAT_MODEL") or "gemini-2.5-flash",
        # Set to an empty string to disable the fallback.
        gemini_fallback_model=os.environ.get("GEMINI_FALLBACK_MODEL", "gemini-2.5-flash-lite"),
        discord_webhook_url=os.environ.get("DISCORD_WEBHOOK_URL", "").strip(),
    )
