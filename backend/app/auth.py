"""Multi-user authentication with PBKDF2 hashes and short-lived HMAC JWTs."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import threading
import time
from typing import Any, Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import db
from .config import (
    ADMIN_PASSWORD,
    ADMIN_USERNAME,
    AUTH_ENABLED,
    SECRET_KEY,
    TOKEN_TTL_SECONDS,
)
from .utils import new_id

bearer = HTTPBearer(auto_error=False)
_failures: dict[str, list[float]] = {}
_fail_lock = threading.Lock()

ROLES = ("admin", "analyst", "viewer")
WRITE_ROLES = ("admin", "analyst")


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


def _public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": user["id"],
        "username": user["username"],
        "email": user.get("email") or "",
        "role": user["role"],
        "disabled": bool(user.get("disabled", False)),
    }


def _validate_credentials(username: str, password: str) -> None:
    if len(username.strip()) < 3:
        raise ValueError("Username must be at least 3 characters")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")


def bootstrap_users() -> None:
    """Seed the environment admin or migrate the legacy single-admin hash."""
    db.init_db()
    if db.get_user_by_username(ADMIN_USERNAME):
        return
    if ADMIN_PASSWORD:
        db.create_user(new_id("usr_"), ADMIN_USERNAME, None, hash_password(ADMIN_PASSWORD), "admin")
        return
    if db.count_users():
        return
    legacy_hash = db.get_setting("admin_password_hash")
    if legacy_hash:
        db.create_user(new_id("usr_"), ADMIN_USERNAME, None, legacy_hash, "admin")


# Kept as an alias for older deployments that call this at startup.
ensure_admin_password = bootstrap_users


def create_token(user: dict[str, Any]) -> str:
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user["username"],
        "uid": user["id"],
        "role": user["role"],
        "iat": now,
        "exp": now + TOKEN_TTL_SECONDS,
    }
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


def _clear_failures(key: str) -> None:
    with _fail_lock:
        _failures.pop(key, None)


def register_first_admin(username: str, email: str, password: str) -> tuple[str, dict[str, Any]]:
    if db.count_users():
        raise ValueError("Accounts already exist. Ask an administrator to add you.")
    _validate_credentials(username, password)
    user = db.create_user(
        new_id("usr_"), username, email, hash_password(password), "admin"
    )
    return create_token(user), _public_user(user)


def register_user(
    username: str, email: str, password: str, role: str = "analyst"
) -> dict[str, Any]:
    _validate_credentials(username, password)
    if role not in ROLES:
        raise ValueError(f"Role must be one of: {', '.join(ROLES)}")
    try:
        return db.create_user(
            new_id("usr_"), username, email, hash_password(password), role
        )
    except Exception as exc:
        raise ValueError("Username or email is already in use") from exc


def authenticate(
    username: str, password: str, client_key: str = "unknown"
) -> tuple[str | None, dict[str, Any] | None]:
    key = f"{client_key}:{username.lower()}"
    if _rate_limited(key):
        return None, None
    user = db.get_user_by_username(username)
    if not user or user["disabled"] or not verify_password(password, user["password_hash"]):
        _record_failure(key)
        return None, None
    db.touch_login(user["id"])
    _clear_failures(key)
    return create_token(user), _public_user(user)


def change_password(
    user_id: str, new_password: str, current_password: str | None = None
) -> None:
    if len(str(new_password or "")) < 8:
        raise ValueError("Password must be at least 8 characters")
    user = db.get_user_by_id(user_id)
    if not user:
        raise ValueError("User not found")
    if current_password is not None and not verify_password(
        current_password, user["password_hash"]
    ):
        raise ValueError("Current password is incorrect")
    db.set_user_password(user_id, hash_password(new_password))


async def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> dict[str, Any]:
    if not AUTH_ENABLED:
        return {
            "id": "local",
            "username": "demo",
            "email": "",
            "role": "admin",
            "disabled": False,
        }
    if creds is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )
    payload = decode_token(creds.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        )
    user = db.get_user_by_id(str(payload.get("uid", "")))
    if not user or user["disabled"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Account is unavailable"
        )
    return _public_user(user)


def require_roles(*roles: str) -> Callable[..., Any]:
    async def dependency(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        if user["role"] not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
            )
        return user

    return dependency


require_admin = require_roles("admin")
require_writer = require_roles(*WRITE_ROLES)
