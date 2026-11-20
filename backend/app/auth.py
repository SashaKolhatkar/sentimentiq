"""Optional single-tenant authentication with PBKDF2 + short-lived HMAC JWTs."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import threading
import time
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import ADMIN_PASSWORD, ADMIN_USERNAME, AUTH_ENABLED, SECRET_KEY, TOKEN_TTL_SECONDS

bearer = HTTPBearer(auto_error=False)
_failures: dict[str, list[float]] = {}
_fail_lock = threading.Lock()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 240_000)
    return f"pbkdf2_sha256$240000${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, rounds, salt, digest = encoded.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        candidate = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), _unb64(salt), int(rounds)
        )
        return hmac.compare_digest(candidate, _unb64(digest))
    except Exception:
        return False


def ensure_admin_password() -> str | None:
    """Persist a hash of the configured admin password on first run."""
    if not ADMIN_PASSWORD:
        return None
    from .db import _connect, _lock

    with _lock, _connect() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        row = conn.execute(
            "SELECT value FROM settings WHERE key='admin_password_hash'"
        ).fetchone()
        if row:
            return row["value"]
        encoded = hash_password(ADMIN_PASSWORD)
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('admin_password_hash', ?)",
            (encoded,),
        )
        return encoded


def create_token(username: str) -> str:
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"sub": username, "iat": now, "exp": now + TOKEN_TTL_SECONDS}
    head = _b64(json.dumps(header, separators=(",", ":")).encode())
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    signature = _b64(
        hmac.new(SECRET_KEY.encode(), f"{head}.{body}".encode(), hashlib.sha256).digest()
    )
    return f"{head}.{body}.{signature}"


def decode_token(token: str) -> dict[str, Any] | None:
    try:
        head, body, signature = token.split(".")
        expected = _b64(
            hmac.new(SECRET_KEY.encode(), f"{head}.{body}".encode(), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(signature, expected):
            return None
        payload = json.loads(_unb64(body))
        if payload.get("exp", 0) < int(time.time()):
            return None
        return payload
    except Exception:
        return None


def _rate_limited(key: str) -> bool:
    now = time.time()
    with _fail_lock:
        attempts = [t for t in _failures.get(key, []) if now - t < 900]
        _failures[key] = attempts
        return len(attempts) >= 10


def _record_failure(key: str) -> None:
    with _fail_lock:
        _failures.setdefault(key, []).append(time.time())


def authenticate(username: str, password: str, client_key: str = "local") -> str | None:
    if _rate_limited(client_key):
        return None
    encoded = ensure_admin_password()
    if not encoded:
        return None
    valid = hmac.compare_digest(username, ADMIN_USERNAME) and verify_password(
        password, encoded
    )
    if not valid:
        _record_failure(client_key)
        return None
    with _fail_lock:
        _failures.pop(client_key, None)
    return create_token(username)


async def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> dict[str, str] | None:
    if not AUTH_ENABLED:
        return {"username": "demo", "role": "demo"}
    if creds is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )
    payload = decode_token(creds.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        )
    return {"username": payload["sub"], "role": "admin"}
