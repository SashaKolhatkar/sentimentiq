"""Safe, validated ingestion for pasted text, files and public web pages."""

from __future__ import annotations

import html
import ipaddress
import re
import socket
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib import robotparser

import pandas as pd

from . import config, store
from .utils import new_id, normalize_text, safe_filename, truncate

TEXT_COLUMNS = ["text", "content", "comment", "review", "post", "message", "body", "description", "caption", "tweet"]
PLATFORM_COLUMNS = ["platform", "source", "site", "network", "channel"]
AUTHOR_COLUMNS = ["author", "user", "username", "user_name", "account", "handle", "reviewer"]
TIME_COLUMNS = ["timestamp", "date", "created_at", "time", "datetime", "published_at", "posted_at"]
ID_COLUMNS = ["id", "review_id", "comment_id", "post_id", "tweet_id"]
META_COLUMNS = {
    "likes": ["likes", "like_count", "favorite_count", "favourites"],
    "replies": ["replies", "reply_count", "comment_count", "retweets", "comments"],
    "followers": ["followers", "follower_count"],
    "following": ["following", "following_count"],
    "account_age_days": ["account_age_days", "account_age", "age_days"],
    "posts_per_day": ["posts_per_day", "daily_posts", "posting_frequency"],
    "verified": ["verified", "is_verified"],
    "engagement_rate": ["engagement_rate", "engagement"],
}


def _pick_column(columns: list[str], candidates: list[str]) -> str | None:
    lowered = {str(c).strip().lower(): c for c in columns}
    for candidate in candidates:
        if candidate in lowered:
            return lowered[candidate]
    for col in columns:
        clean = re.sub(r"[^a-z]", "", str(col).lower())
        for candidate in candidates:
            if candidate.replace("_", "") in clean:
                return col
    return None


def _clean_cell(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def _metadata_from_row(row: pd.Series, columns: list[str]) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    for key, candidates in META_COLUMNS.items():
        col = _pick_column(columns, candidates)
        if not col:
            continue
        value = row.get(col)
        if value is None or (isinstance(value, float) and pd.isna(value)):
            continue
        raw = str(value).strip()
        if key == "verified":
            meta[key] = raw.lower() in {"true", "1", "yes", "y", "verified"}
        else:
            try:
                meta[key] = float(raw.replace(",", ""))
            except ValueError:
                continue
    return meta


def _warn_once(warnings: list[str], seen: set[str], message: str) -> None:
    if message not in seen:
        seen.add(message)
        warnings.append(message)


def _frame_records(frame: pd.DataFrame, path: Path, warnings: list[str], seen: set[str], offset: int):
    columns = list(frame.columns)
    text_col = _pick_column(columns, TEXT_COLUMNS)
    if text_col is None and columns:
        text_col = columns[0]
        _warn_once(warnings, seen, f"No recognised text column; using '{text_col}'.")
    if text_col is None:
        _warn_once(warnings, seen, "The file has no columns.")
        return

    platform_col = _pick_column(columns, PLATFORM_COLUMNS)
    author_col = _pick_column(columns, AUTHOR_COLUMNS)
    time_col = _pick_column(columns, TIME_COLUMNS)
    id_col = _pick_column(columns, ID_COLUMNS)

    for idx, row in frame.iterrows():
        text = _clean_cell(row.get(text_col))
        if not text or len(text) < 2:
            continue
        yield {
            "id": _clean_cell(row.get(id_col)) if id_col else f"f-{offset + idx + 1}",
            "text": text,
            "platform": _clean_cell(row.get(platform_col)) if platform_col else path.stem,
            "author": _clean_cell(row.get(author_col)) if author_col else None,
            "timestamp": _clean_cell(row.get(time_col)) if time_col else None,
            "metadata": _metadata_from_row(row, columns),
            "source_type": "file",
        }


def iter_tabular(path: Path, warnings: list[str], seen: set[str] | None = None):
    """Stream records from a file without materialising the whole dataset."""
    seen = seen if seen is not None else set()
    ext = path.suffix.lower()
    count = 0

    if ext == ".txt":
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for idx, line in enumerate(handle):
                line = line.strip()
                if not line:
                    continue
                yield {"id": f"l-{idx + 1}", "text": line, "source_type": "file"}
                count += 1
                if count >= config.MAX_RECORDS:
                    _warn_once(warnings, seen, f"Only the first {config.MAX_RECORDS} rows were loaded.")
                    return
        return

    if ext == ".csv":
        frames = pd.read_csv(
            path, dtype=str, on_bad_lines="skip", encoding_errors="replace",
            chunksize=config.CHUNK_SIZE,
        )
    else:
        frames = [pd.read_excel(path, dtype=str)]

    offset = 0
    for frame in frames:
        for record in _frame_records(frame, path, warnings, seen, offset):
            yield record
            count += 1
            if count >= config.MAX_RECORDS:
                _warn_once(warnings, seen, f"Only the first {config.MAX_RECORDS} rows were loaded.")
                return
        offset += len(frame)


def parse_tabular(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Compatibility wrapper used by scripts and small files."""
    warnings: list[str] = []
    return list(iter_tabular(path, warnings)), warnings


def parse_pasted_text(text: str, split_lines: bool, platform: str = "manual") -> list[dict[str, Any]]:
    cleaned = str(text or "").replace("\r\n", "\n").strip()
    if not cleaned:
        return []
    if split_lines:
        parts = [ln.strip() for ln in cleaned.split("\n") if ln.strip()]
    else:
        parts = [p.strip() for p in re.split(r"\n\s*\n", cleaned) if p.strip()]
    return [
        {
            "id": f"m-{i + 1}",
            "text": part,
            "platform": platform,
            "author": None,
            "timestamp": None,
            "source_type": "paste",
        }
        for i, part in enumerate(parts[: config.MAX_RECORDS])
    ]


def _host_allowed(host: str) -> bool:
    host = host.lower().rstrip(".")
    for domain in config.ALLOWED_URL_DOMAINS:
        if host == domain or host.endswith("." + domain):
            return True
    return False


def _validate_url(url: str) -> tuple[str, str]:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http and https URLs are supported.")
    host = parsed.hostname or ""
    if not host:
        raise ValueError("The URL has no hostname.")
    if not _host_allowed(host):
        raise ValueError(
            "This domain is not in the allowlist. Supported domains: "
            + ", ".join(config.ALLOWED_URL_DOMAINS)
        )
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
        for info in infos:
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                raise ValueError("URLs pointing to private or local addresses are blocked.")
    except socket.gaierror as exc:
        raise ValueError(f"Could not resolve the hostname: {exc}") from exc
    return url, host


def _robots_allows(url: str, host: str) -> tuple[bool, bool]:
    parser = robotparser.RobotFileParser()
    base = f"{urlparse(url).scheme}://{host}/robots.txt"
    try:
        import httpx

        response = httpx.get(base, timeout=min(config.URL_FETCH_TIMEOUT, 8), follow_redirects=False)
        if response.status_code >= 400:
            return True, False
        parser.parse(response.text.splitlines())
        return parser.can_fetch("*", url), True
    except Exception:
        return True, False


def fetch_public_page(url: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Fetch a robots-respecting public page and extract review-like text blocks.

    This is intentionally generic.  It does not bypass logins, rate limits or
    platform APIs; blocked pages return a clear error instead of fake records.
    """
    url, host = _validate_url(url)
    warnings: list[str] = []
    allowed, robots_found = _robots_allows(url, host)
    if not allowed:
        raise ValueError("robots.txt disallows automated access to this page.")
    if not robots_found:
        warnings.append("No robots.txt was reachable; access was allowed by default.")

    import httpx

    headers = {
        "User-Agent": "SentimentIQ/1.0 (+research; respects robots.txt)",
        "Accept": "text/html,application/xhtml+xml",
    }
    with httpx.stream(
        "GET", url, headers=headers, timeout=config.URL_FETCH_TIMEOUT,
        follow_redirects=False, max_redirects=0,
    ) as response:
        if response.status_code >= 300:
            raise ValueError(f"The page returned HTTP {response.status_code}.")
        content_type = response.headers.get("content-type", "")
        if "html" not in content_type and "text" not in content_type:
            raise ValueError("Only HTML/text pages can be ingested from a URL.")
        chunks: list[bytes] = []
        size = 0
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > config.URL_MAX_BYTES:
                warnings.append("Page was truncated to the configured size limit.")
                break
            chunks.append(chunk)
    raw = b"".join(chunks).decode("utf-8", errors="replace")
    blocks: list[str] = []
    for pattern in (
        r"<(?:p|li|blockquote|div)[^>]*class=[\"'][^\"']*(?:review|comment|post|content|body)[^\"']*[\"'][^>]*>(.*?)</(?:p|li|blockquote|div)>",
        r"<(?:p|li|blockquote)[^>]*>(.*?)</(?:p|li|blockquote)>",
    ):
        for match in re.findall(pattern, raw, flags=re.I | re.S):
            text = normalize_text(html.unescape(re.sub(r"<[^>]+>", " ", match)))
            if 20 <= len(text) <= 1500:
                blocks.append(text)
    if not blocks:
        plain = normalize_text(re.sub(r"<[^>]+>", "\n", raw))
        blocks = [ln for ln in plain.split("\n") if 20 <= len(ln) <= 1500]

    seen: set[str] = set()
    records: list[dict[str, Any]] = []
    for block in blocks:
        key = re.sub(r"\W+", "", block.lower())[:200]
        if key in seen:
            continue
        seen.add(key)
        records.append(
            {
                "id": new_id("u-"),
                "text": truncate(block, config.MAX_TEXT_LENGTH),
                "platform": host.replace("www.", ""),
                "author": None,
                "timestamp": None,
                "source_type": "url",
            }
        )
        if len(records) >= 300:
            warnings.append("Only the first 300 text blocks were loaded.")
            break

    if not records:
        raise ValueError("No review-like text blocks could be extracted from this page.")
    warnings.append(
        "Public page content was read under its access rules. No private API or authenticated data was used."
    )
    return records, warnings


def _iter_upload_records(upload: Any, warnings: list[str], state: dict[str, Any]):
    filename = safe_filename(getattr(upload, "filename", "") or "upload")
    ext = Path(filename).suffix.lower()
    if ext not in config.ALLOWED_EXTENSIONS:
        warnings.append(f"{filename}: unsupported file type ({ext or 'none'}).")
        return
    temp = config.UPLOAD_DIR / f"{new_id('up_')}_{filename}"
    limit = config.MAX_FILE_SIZE_MB * 1024 * 1024
    written = 0
    valid = True
    try:
        with temp.open("wb") as output:
            while True:
                chunk = upload.file.read(1 << 20)
                if not chunk:
                    break
                written += len(chunk)
                if written > limit:
                    warnings.append(f"{filename}: exceeds the {config.MAX_FILE_SIZE_MB} MB limit.")
                    valid = False
                    break
                output.write(chunk)
        if not valid or not written:
            if valid:
                warnings.append(f"{filename}: file is empty.")
            return
        parse_warnings: list[str] = []
        yield from iter_tabular(temp, parse_warnings)
        warnings.extend(f"{filename}: {w}" for w in parse_warnings)
        state["source_type"] = "file"
    finally:
        temp.unlink(missing_ok=True)


def build_preview(
    text: str = "",
    split_lines: bool = True,
    files: list[Any] | None = None,
    url: str = "",
    platform: str = "manual",
) -> dict[str, Any]:
    """Parse inputs once, stage them to disk, and return only preview metadata."""
    warnings: list[str] = []
    state: dict[str, Any] = {
        "source_type": "manual",
        "with_timestamps": 0,
        "with_authors": 0,
        "with_metadata": 0,
        "platforms": set(),
    }

    def source_records():
        if text.strip():
            state["source_type"] = "paste"
            for record in parse_pasted_text(text, split_lines, platform):
                yield record
        for upload in files or []:
            if not upload or not getattr(upload, "filename", None):
                continue
            yield from _iter_upload_records(upload, warnings, state)
        if url.strip():
            try:
                parsed, url_warnings = fetch_public_page(url.strip())
                warnings.extend(url_warnings)
                state["source_type"] = "url"
                yield from parsed
            except ValueError as exc:
                warnings.append(f"URL: {exc}")

    def counted_records():
        for record in source_records():
            if not normalize_text(record.get("text", "")):
                continue
            if record.get("timestamp"):
                state["with_timestamps"] += 1
            if record.get("author"):
                state["with_authors"] += 1
            if record.get("metadata"):
                state["with_metadata"] += 1
            state["platforms"].add(record.get("platform") or "unknown")
            yield record

    dataset_id, total = store.create_dataset(counted_records(), state["source_type"])

    preview: list[dict[str, Any]] = []
    inline_records: list[dict[str, Any]] = []
    include_inline = total <= config.INLINE_RECORD_LIMIT
    for idx, record in enumerate(store.iter_dataset(dataset_id)):
        if idx < 10:
            preview.append({
                "id": record.get("id"),
                "text": truncate(str(record.get("text") or ""), 300),
                "platform": record.get("platform") or "unknown",
                "author": record.get("author"),
                "timestamp": record.get("timestamp"),
                "has_metadata": bool(record.get("metadata")),
            })
        if include_inline:
            inline_records.append(record)

    payload: dict[str, Any] = {
        "dataset_id": dataset_id,
        "count": total,
        "preview": preview,
        "warnings": warnings,
        "source_type": state["source_type"],
        "counts": {
            "total": total,
            "with_timestamps": state["with_timestamps"],
            "with_authors": state["with_authors"],
            "with_metadata": state["with_metadata"],
            "platforms": sorted(state["platforms"]),
        },
    }
    if include_inline:
        # Small inputs remain compatible with older API clients.
        payload["records"] = inline_records
    return payload
