"""Small shared helpers: JSON safety, text cleanup, PII redaction, IDs."""

from __future__ import annotations

import hashlib
import html
import math
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

URL_RE = re.compile(r"https?://\S+", re.I)
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)")
CARD_RE = re.compile(r"(?<!\d)(?:\d[ -]*?){13,19}(?!\d)")
MENTION_RE = re.compile(r"(?<!\w)@[\w.]+")
HASHTAG_RE = re.compile(r"(?<!\w)#[\w]+")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


def to_jsonable(value: Any) -> Any:
    """Recursively convert numpy/pandas objects into JSON-safe primitives."""
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        f = float(value)
        return None if not math.isfinite(f) else round(f, 6)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, float):
        return None if not math.isfinite(value) else round(value, 6)
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return to_jsonable(value.item())
        except Exception:
            pass
    return value


def strip_html(raw: str) -> str:
    text = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", raw, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = text.replace("\u00a0", " ")
    return re.sub(r"[ \t]+", " ", text).strip()


def redact_pii(text: str) -> str:
    """Replace obvious PII before text is sent to a model or stored in a report."""
    if not text:
        return ""
    out = EMAIL_RE.sub("[email]", text)
    out = CARD_RE.sub("[number]", out)
    out = PHONE_RE.sub("[phone]", out)
    return out


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", strip_html(str(text or ""))).strip()


def text_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def safe_filename(name: str) -> str:
    base = Path(name).name if name else "upload"
    return re.sub(r"[^A-Za-z0-9._-]", "_", base)[:120]


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        f = float(value)
        return f if math.isfinite(f) else default
    except (TypeError, ValueError):
        return default


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def pct(value: float) -> float:
    return round(clamp(value) * 100, 1)


def split_clauses(text: str) -> list[str]:
    """Split on contrast markers so aspect-level sentiment stays local."""
    parts = re.split(
        r"(?:\s+(?:but|however|though|although|yet|whereas|while|except)\s+|\s*[;|]\s*|"
        r"(?<=[.!?])\s+(?=[A-Z]))",
        str(text or ""),
        flags=re.I,
    )
    return [p.strip() for p in parts if len(p.strip()) > 2]


def truncate(text: str, length: int = 240) -> str:
    text = str(text or "")
    return text if len(text) <= length else text[: length - 1].rstrip() + "…"
