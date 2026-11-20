"""Scalable JSONL storage for staged uploads and enriched analysis records.

Large datasets are never sent to the browser as one JSON document. Ingestion
writes records to disk once, analysis streams them, and the UI reads pages from
the server. This keeps memory bounded regardless of dataset size.
"""

from __future__ import annotations

import csv
import heapq
import io
import json
import tempfile
import threading
from pathlib import Path
from typing import Any, Iterable, Iterator

from . import config, db
from .utils import new_id, to_jsonable

_Lock = threading.RLock()
_OFFSET_CACHE: dict[str, list[int]] = {}


def _dump(record: dict[str, Any]) -> str:
    return json.dumps(to_jsonable(record), ensure_ascii=False, separators=(",", ":"))


def _load(line: str) -> dict[str, Any]:
    return json.loads(line)


# ---------------------------------------------------------------------------
# Staged source datasets
# ---------------------------------------------------------------------------


def dataset_path(dataset_id: str) -> Path:
    if not dataset_id or not dataset_id.startswith("ds_") or any(not (c.isalnum() or c == "_") for c in dataset_id):
        raise ValueError("Invalid dataset id")
    return config.DATASET_DIR / f"{dataset_id}.jsonl"


def create_dataset(records: Iterable[dict[str, Any]], source_type: str, is_demo: bool = False) -> tuple[str, int]:
    """Persist an iterable of records and return (dataset_id, count)."""
    dataset_id = new_id("ds_")
    path = dataset_path(dataset_id)
    tmp = path.with_suffix(".tmp")
    count = 0
    try:
        with _Lock, tmp.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(_dump(record) + "\n")
                count += 1
        tmp.replace(path)
        db.create_dataset(dataset_id, count, source_type, is_demo)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return dataset_id, count


def iter_dataset(dataset_id: str) -> Iterator[dict[str, Any]]:
    path = dataset_path(dataset_id)
    if not path.exists():
        raise FileNotFoundError("Dataset not found or expired")
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield _load(line)


def dataset_meta(dataset_id: str) -> dict[str, Any] | None:
    return db.get_dataset(dataset_id)


def delete_dataset(dataset_id: str) -> bool:
    path = dataset_path(dataset_id)
    path.unlink(missing_ok=True)
    return db.delete_dataset(dataset_id)


# ---------------------------------------------------------------------------
# Enriched run records
# ---------------------------------------------------------------------------


def run_records_path(run_id: str) -> Path:
    if not run_id or not run_id.startswith("run_") or any(not (c.isalnum() or c == "_") for c in run_id):
        raise ValueError("Invalid run id")
    return config.RUN_DIR / f"{run_id}.jsonl"


class RecordWriter:
    """Streaming writer used by the analysis pipeline."""

    def __init__(self, run_id: str) -> None:
        self.path = run_records_path(run_id)
        self.tmp = self.path.with_suffix(".tmp")
        self._handle = self.tmp.open("w", encoding="utf-8")
        self.count = 0

    def write(self, record: dict[str, Any]) -> None:
        self._handle.write(_dump(record) + "\n")
        self.count += 1

    def close(self, commit: bool = True) -> None:
        self._handle.close()
        if commit:
            self.tmp.replace(self.path)
            with _Lock:
                _OFFSET_CACHE.pop(self.path.stem, None)
        else:
            self.tmp.unlink(missing_ok=True)


def _offset_index(path: Path) -> list[int]:
    key = path.stem
    with _Lock:
        cached = _OFFSET_CACHE.get(key)
        if cached is not None:
            return cached
    offsets = [0]
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1 << 20)
            if not chunk:
                break
            start = 0
            while True:
                idx = chunk.find(b"\n", start)
                if idx < 0:
                    break
                offsets.append(handle.tell() - len(chunk) + idx + 1)
                start = idx + 1
    with _Lock:
        _OFFSET_CACHE[key] = offsets
    return offsets


def _matches(record: dict[str, Any], filters: dict[str, str]) -> bool:
    q = filters.get("q", "").strip().lower()
    if q and q not in " ".join(
        str(record.get(k) or "") for k in ("text", "author", "platform", "id")
    ).lower():
        return False
    for key, field in (
        ("sentiment", "sentiment"), ("emotion", "emotion"),
        ("platform", "platform"), ("spam", "spam_label"), ("bot", "automation_label"),
    ):
        wanted = filters.get(key, "all")
        if wanted and wanted != "all":
            if wanted == "flagged" and key == "spam":
                if record.get("spam_label") == "Likely Genuine":
                    return False
            elif str(record.get(field) or "") != wanted:
                return False
    return True


def _sort_rank(record: dict[str, Any], idx: int, sort: str) -> tuple[Any, ...]:
    """Rank tuple; ascending order is the requested display order."""
    timestamp = str(record.get("timestamp") or "")
    record_id = str(record.get("id") or "")
    if sort == "newest":
        return (timestamp, record_id, idx)
    if sort == "score":
        return (float(record.get("sentiment_score") or 0), timestamp, idx)
    if sort == "suspicion":
        return (float(record.get("suspicion_score") or 0), timestamp, idx)
    return (idx,)


def _is_reversed(sort: str) -> bool:
    return sort in {"newest", "suspicion"}


class _SortItem:
    __slots__ = ("rank", "idx", "record")

    def __init__(self, rank: tuple[Any, ...], idx: int, record: dict[str, Any]) -> None:
        self.rank = rank
        self.idx = idx
        self.record = record


class _AscItem(_SortItem):
    def __lt__(self, other: "_SortItem") -> bool:
        return (self.rank, self.idx) < (other.rank, other.idx)


class _DescItem(_SortItem):
    def __lt__(self, other: "_SortItem") -> bool:
        return (self.rank, self.idx) > (other.rank, other.idx)


def _iter_matching(run_id: str, filters: dict[str, str] | None) -> Iterator[dict[str, Any]]:
    path = run_records_path(run_id)
    if not path.exists():
        raise FileNotFoundError("Analysis records not found")
    filters = filters or {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = _load(line)
            if _matches(record, filters):
                yield record


def _sorted_records(
    run_id: str,
    filters: dict[str, str] | None,
    sort: str,
) -> Iterator[dict[str, Any]]:
    """External merge sort so sorted exports stay memory-bounded."""
    reverse = _is_reversed(sort)
    wrapper = _DescItem if reverse else _AscItem
    paths: list[Path] = []
    buffer: list[tuple[tuple[Any, ...], int, dict[str, Any]]] = []

    with tempfile.TemporaryDirectory(dir=config.RUN_DIR, prefix="sort_") as folder:
        temp_dir = Path(folder)

        def flush() -> None:
            if not buffer:
                return
            buffer.sort(key=lambda item: item[0], reverse=reverse)
            path = temp_dir / f"chunk_{len(paths):05d}.jsonl"
            with path.open("w", encoding="utf-8") as handle:
                for rank, idx, record in buffer:
                    handle.write(json.dumps([rank, idx, record], ensure_ascii=False, separators=(",", ":")) + "\n")
            paths.append(path)
            buffer.clear()

        for idx, record in enumerate(_iter_matching(run_id, filters)):
            buffer.append((_sort_rank(record, idx, sort), idx, record))
            if len(buffer) >= config.SORT_CHUNK_SIZE:
                flush()
        flush()

        def reader(path: Path) -> Iterator[_SortItem]:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    rank, idx, record = json.loads(line)
                    yield wrapper(tuple(rank), int(idx), record)

        for item in heapq.merge(*(reader(path) for path in paths)):
            yield item.record


def query_run_records(
    run_id: str,
    offset: int = 0,
    limit: int = 10,
    filters: dict[str, str] | None = None,
    sort: str = "newest",
) -> dict[str, Any]:
    """Return a page plus the total number of matching records."""
    path = run_records_path(run_id)
    if not path.exists():
        raise FileNotFoundError("Analysis records not found")
    filters = filters or {}
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    has_filters = any(v and v != "all" for k, v in filters.items() if k != "q") or bool(filters.get("q"))

    if not has_filters and sort == "index":
        offsets = _offset_index(path)
        total = max(0, len(offsets) - 1)
        page: list[dict[str, Any]] = []
        if offset < total:
            with path.open("rb") as handle:
                handle.seek(offsets[offset])
                for _ in range(min(limit, total - offset)):
                    line = handle.readline()
                    if line:
                        page.append(_load(line))
        return {"records": page, "total": total, "offset": offset, "limit": limit}

    if sort == "index":
        iterator: Iterator[dict[str, Any]] = _iter_matching(run_id, filters)
    else:
        iterator = _sorted_records(run_id, filters, sort)

    total = 0
    page = []
    target = offset + limit
    for record in iterator:
        if offset <= total < target:
            page.append(record)
        total += 1
    return {"records": page, "total": total, "offset": offset, "limit": limit}


def iter_filtered_records(
    run_id: str,
    filters: dict[str, str] | None = None,
    sort: str = "index",
    max_records: int | None = None,
) -> Iterator[dict[str, Any]]:
    """Stream matching records for CSV/Excel export without loading the run into RAM."""
    run_records_path(run_id)  # validates the id
    iterator: Iterator[dict[str, Any]]
    if sort == "index":
        iterator = _iter_matching(run_id, filters)
    else:
        iterator = _sorted_records(run_id, filters, sort)

    emitted = 0
    for record in iterator:
        yield record
        emitted += 1
        if max_records and emitted >= max_records:
            return


def delete_run_records(run_id: str) -> bool:
    path = run_records_path(run_id)
    existed = path.exists()
    path.unlink(missing_ok=True)
    config.RUN_DIR.joinpath(f"{run_id}.tmp").unlink(missing_ok=True)
    with _Lock:
        _OFFSET_CACHE.pop(run_id, None)
    return existed


RECORD_COLUMNS = [
    ("ID", "id"), ("Text", "text"), ("Platform", "platform"), ("Author", "author"),
    ("Timestamp", "timestamp"), ("Sentiment", "sentiment"),
    ("Sentiment Score", "sentiment_score"), ("Sentiment Confidence", "sentiment_confidence"),
    ("Emotion", "emotion"), ("Emotion Confidence", "emotion_confidence"),
    ("Spam Label", "spam_label"), ("Suspicion Score", "suspicion_score"),
    ("Spam Uncertainty", "spam_uncertainty"), ("Spam Reasons", "spam_reasons"),
    ("Automation Label", "automation_label"), ("Automation Score", "automation_score"),
    ("Automation Indicators", "automation_indicators"),
]


def _cell(value: Any, key: str) -> Any:
    if value is None:
        return ""
    if key in {"spam_reasons"}:
        return "; ".join(str(v) for v in value)
    if key == "automation_indicators":
        return "; ".join(str(i.get("name", "")) for i in value if isinstance(i, dict))
    return value


def records_csv(records: Iterable[dict[str, Any]]) -> bytes:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([name for name, _ in RECORD_COLUMNS])
    for record in records:
        writer.writerow([_cell(record.get(key), key) for _, key in RECORD_COLUMNS])
    return output.getvalue().encode("utf-8-sig")
