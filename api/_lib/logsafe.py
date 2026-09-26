"""Logging that never prints secrets.

Every record is fully formatted (message, args and traceback), then scrubbed of:
- the exact values of our server secrets (Gemini key, service-role key, Discord webhook, DB URL
  and password), and
- anything shaped like a secret (Google API keys, Discord webhook URLs, JWTs, passwords in
  connection strings, key/token query parameters).
Tracebacks matter most: an httpx error message can contain the webhook URL it was calling.
"""

import logging
import re
from urllib.parse import unquote, urlsplit

from .config import get_settings

MASK = "[REDACTED]"

_PATTERNS = [
    (re.compile(r"https://(?:discord|discordapp)\.com/api/webhooks/\S+"), MASK),
    (re.compile(r"AIza[0-9A-Za-z_\-]{30,}"), MASK),
    (re.compile(r"eyJ[\w-]{8,}\.[\w-]{8,}\.[\w-]{8,}"), MASK),  # JWTs (service-role key, user tokens)
    (re.compile(r"sb_(?:secret|publishable)_[\w-]{10,}"), MASK),
    (re.compile(r"(://[^:/@\s]+:)[^@\s]+(@)"), rf"\g<1>{MASK}\g<2>"),  # password in URLs, keep user
    (re.compile(r"(?i)([?&](?:key|token|apikey)=)[^&\s]+"), rf"\g<1>{MASK}"),
]


def _secret_values() -> list[str]:
    try:
        s = get_settings()
    except Exception:  # settings missing (e.g. during early import): patterns still apply
        return []
    values = [s.gemini_api_key, s.supabase_service_role_key, s.discord_webhook_url, s.database_url]
    try:
        password = urlsplit(s.database_url).password
        if password:
            values += [password, unquote(password)]
    except ValueError:
        pass
    # Longest first so a value containing another is masked whole.
    return sorted({v for v in values if v and len(v) >= 6}, key=len, reverse=True)


def redact(text: str) -> str:
    for value in _secret_values():
        text = text.replace(value, MASK)
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = None
        if record.exc_info:
            record.exc_text = redact(logging.Formatter().formatException(record.exc_info))
            record.exc_info = None
        if record.stack_info:
            record.stack_info = redact(record.stack_info)
        return True


def install() -> None:
    """Route app logs through a redacting handler (idempotent)."""
    root = logging.getLogger()
    if any(isinstance(f, RedactingFilter) for h in root.handlers for f in h.filters):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    handler.addFilter(RedactingFilter())
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    # Per-request lines from HTTP clients are noise (and a place URLs could leak); keep warnings.
    for noisy in ("httpx", "httpcore", "google_genai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    # uvicorn's own handlers too (it logs errors with tracebacks outside our loggers).
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        for h in logging.getLogger(name).handlers:
            h.addFilter(RedactingFilter())
