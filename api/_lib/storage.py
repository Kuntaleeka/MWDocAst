"""Supabase Storage via its REST API, using the service-role key (server only)."""

import httpx

from .config import get_settings

BUCKET = "documents"


class StorageError(RuntimeError):
    pass


def _base() -> tuple[str, dict[str, str]]:
    s = get_settings()
    key = s.supabase_service_role_key
    return f"{s.supabase_url.rstrip('/')}/storage/v1", {"Authorization": f"Bearer {key}", "apikey": key}


def create_signed_upload(path: str) -> str:
    """Returns the token the browser passes to supabase-js `uploadToSignedUrl` (valid ~2h)."""
    base, headers = _base()
    res = httpx.post(f"{base}/object/upload/sign/{BUCKET}/{path}", headers=headers, timeout=15)
    if res.status_code != 200:
        raise StorageError(f"Could not create upload URL ({res.status_code})")
    url = res.json()["url"]
    return httpx.URL(url).params["token"]


def download(path: str) -> bytes:
    base, headers = _base()
    res = httpx.get(f"{base}/object/{BUCKET}/{path}", headers=headers, timeout=60)
    if res.status_code == 404 or res.status_code == 400:
        raise FileNotFoundError(path)
    if res.status_code != 200:
        raise StorageError(f"Could not download upload ({res.status_code})")
    return res.content


def delete(path: str) -> None:
    base, headers = _base()
    httpx.request("DELETE", f"{base}/object/{BUCKET}", headers=headers, json={"prefixes": [path]}, timeout=15)
