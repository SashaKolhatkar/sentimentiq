"""Automated-account detection from behavioural and account-level signals.

A single signal never produces a strong verdict.  The module aggregates by
author, measures timing regularity, content repetition, coordination across
accounts and metadata, then applies an NLI check to the account summary.
"""

from __future__ import annotations

import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .. import config, models
from ..utils import clamp, normalize_text

LABELS = ["Likely Human", "Possibly Automated", "Strong Automation Indicators", "Insufficient Data"]


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def _similarity_matrix(texts: list[str]) -> np.ndarray:
    if len(texts) < 2:
        return np.zeros((len(texts), len(texts)), dtype=float)
    try:
        matrix = TfidfVectorizer(
            ngram_range=(1, 2), sublinear_tf=True, max_features=30000
        ).fit_transform([t or "empty" for t in texts])
        return cosine_similarity(matrix)
    except Exception:
        return np.zeros((len(texts), len(texts)), dtype=float)


def _nli_account(summary: str) -> dict[str, float] | None:
    try:
        pipe = models.nli_pipeline()
        labels = ["an automated bot account", "a normal human user account",
                  "an account with insufficient activity data"]
        out = pipe(
            summary[:512],
            candidate_labels=labels,
            hypothesis_template="This social media account behaves like {}.",
            truncation=True,
            max_length=512,
        )
        if isinstance(out, list):
            out = out[0]
        mapping = {
            str(k).lower(): float(v)
            for k, v in zip(out.get("labels", []), out.get("scores", []))
        }
        return {
            "bot": mapping.get(labels[0], 0.0),
            "human": mapping.get(labels[1], 0.0),
            "insufficient": mapping.get(labels[2], 0.0),
        }
    except Exception:
        return None


def detect_bots(records: list[dict[str, Any]], texts: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return per-record automation info and per-account summaries."""
    if not records:
        return [], []

    normalized = [normalize_text(t) for t in texts]
    sim = _similarity_matrix(normalized)
    groups: dict[str, list[int]] = defaultdict(list)
    for idx, record in enumerate(records):
        author = str(record.get("author") or f"anon-{record.get('id', idx)}")
        groups[author].append(idx)

    account_summaries: list[dict[str, Any]] = []
    record_info: list[dict[str, Any]] = [{} for _ in records]

    for author, indices in groups.items():
        posts = len(indices)
        unique_ratio = len({normalized[i] for i in indices}) / posts
        times = sorted(t for i in indices if (t := _parse_time(records[i].get("timestamp"))) is not None)
        intervals = [
            (b - a).total_seconds() / 60
            for a, b in zip(times, times[1:])
        ]
        positive_intervals = [i for i in intervals if i > 0]
        interval_cv = (
            statistics.pstdev(positive_intervals) / statistics.fmean(positive_intervals)
            if len(positive_intervals) >= 4 and statistics.fmean(positive_intervals) > 0
            else None
        )
        span_hours = (times[-1] - times[0]).total_seconds() / 3600 if len(times) >= 2 else 0
        rate = posts / span_hours if span_hours > 0 else None

        own_sims = [
            sim[i][j]
            for a, i in enumerate(indices)
            for j in indices[a + 1:]
        ]
        own_similarity = float(np.mean(own_sims)) if own_sims else None

        coordination = 0
        for i in indices:
            peers = [
                float(sim[i][j])
                for j in range(len(records))
                if j not in indices and sim[i][j] >= 0.90
            ]
            if peers:
                coordination += 1

        metadata_available = False
        meta_signals: list[str] = []
        for i in indices:
            meta = records[i].get("metadata") or {}
            if any(k in meta for k in ("account_age_days", "followers", "following", "posts_per_day", "verified")):
                metadata_available = True
            try:
                if float(meta.get("account_age_days", 9999)) < 10:
                    if "very new account" not in meta_signals:
                        meta_signals.append("very new account")
            except (TypeError, ValueError):
                pass
            if meta.get("verified") is False and "unverified account" not in meta_signals:
                meta_signals.append("unverified account")
            if meta.get("posts_per_day") is not None:
                try:
                    if float(meta["posts_per_day"]) > 25 and "very high posting rate" not in meta_signals:
                        meta_signals.append("very high posting rate")
                except (TypeError, ValueError):
                    pass

        indicators: list[dict[str, Any]] = []
        if posts >= 5 and unique_ratio < 0.55:
            indicators.append({"name": "Repeated content", "detail": f"Only {unique_ratio:.0%} of posts are unique.", "weight": 0.30})
        if interval_cv is not None and interval_cv < 0.20:
            indicators.append({"name": "Regular posting intervals", "detail": f"Interval variation (CV) {interval_cv:.2f} across {len(positive_intervals)} gaps.", "weight": 0.26})
        if rate is not None and rate > 8:
            indicators.append({"name": "High posting frequency", "detail": f"Approximately {rate:.1f} posts/hour over the observed window.", "weight": 0.22})
        if own_similarity is not None and own_similarity > 0.62 and posts >= 4:
            indicators.append({"name": "Self-similar posts", "detail": f"Mean pairwise similarity {own_similarity:.2f}.", "weight": 0.24})
        if coordination >= 2:
            indicators.append({"name": "Cross-account coordination", "detail": f"{coordination} post(s) closely mirror posts from other accounts.", "weight": 0.28})
        if "very new account" in meta_signals and posts >= 5:
            indicators.append({"name": "New account with high volume", "detail": "Account age under 10 days with substantial posting volume.", "weight": 0.18})
        if "very high posting rate" in meta_signals:
            indicators.append({"name": "Metadata posting anomaly", "detail": "Declared posts/day is unusually high.", "weight": 0.20})

        summary_bits = [
            f"{posts} posts",
            f"unique content {unique_ratio:.0%}",
        ]
        if interval_cv is not None:
            summary_bits.append(f"timing consistency {interval_cv:.2f} variation")
        if own_similarity is not None:
            summary_bits.append(f"content similarity {own_similarity:.2f}")
        if coordination:
            summary_bits.append(f"{coordination} cross-account matches")
        summary = "; ".join(summary_bits)
        nli = _nli_account(summary) if posts >= 3 or metadata_available else None
        nli_component = 0.18 * clamp((nli["bot"] - nli["human"]) + 0.5) if nli else 0.0
        if nli and nli["bot"] > 0.55:
            indicators.append({"name": "Behaviour model signal", "detail": f"Account summary scored {nli['bot']:.0%} bot-like by NLI model.", "weight": 0.16})

        raw_score = sum(i["weight"] for i in indicators) + nli_component
        score = round(clamp(raw_score), 4)
        evidence_count = len({i["name"] for i in indicators})

        if posts < 3 and not metadata_available:
            label = "Insufficient Data"
            note = "Fewer than 3 posts and no account metadata."
        elif score >= 0.72 and evidence_count >= 3:
            label = "Strong Automation Indicators"
            note = "Multiple independent behavioural signals agree."
        elif (score >= 0.40 and evidence_count >= 2) or (score >= 0.50 and evidence_count == 1):
            label = "Possibly Automated"
            note = (
                "Based on multiple signals." if evidence_count >= 2
                else "Only one strong signal; confidence is low."
            )
        else:
            label = "Likely Human"
            note = "No sufficient automation pattern in available data."

        uncertainty = 0.18 + (0.20 if posts < 5 else 0) + (0.18 if not metadata_available else 0) + (
            0.14 if nli is None else 0
        )
        if evidence_count == 1:
            uncertainty += 0.20
        account = {
            "author": author,
            "posts": posts,
            "label": label,
            "score": score,
            "confidence": round(clamp(1 - min(uncertainty, 0.85)), 3),
            "uncertainty": round(clamp(uncertainty), 3),
            "note": note,
            "indicators": indicators,
            "signals": {
                "unique_content_ratio": round(unique_ratio, 3),
                "interval_cv": round(interval_cv, 3) if interval_cv is not None else None,
                "posts_per_hour": round(rate, 2) if rate is not None else None,
                "mean_self_similarity": round(own_similarity, 3) if own_similarity is not None else None,
                "cross_account_matches": coordination,
                "metadata_available": metadata_available,
                "metadata_signals": meta_signals,
            },
        }
        account_summaries.append(account)
        for i in indices:
            record_info[i] = {
                "label": label,
                "score": score,
                "indicators": indicators,
                "author": author,
                "note": note,
            }

    account_summaries.sort(key=lambda a: (-a["score"], a["author"]))
    return record_info, account_summaries


# ---------------------------------------------------------------------------
# Streaming account aggregation for large datasets.  State per author is
# compact and bounded; a full pairwise similarity matrix is never built.
# ---------------------------------------------------------------------------


class _AccountState:
    __slots__ = (
        "posts", "unique", "unique_capped", "times", "signatures",
        "metadata_available", "meta_signals", "max_posts_per_day",
        "verified_false",
    )

    def __init__(self) -> None:
        self.posts = 0
        self.unique: set[str] = set()
        self.unique_capped = False
        self.times: list[datetime] = []
        self.signatures: Counter = Counter()
        self.metadata_available = False
        self.meta_signals: set[str] = set()
        self.max_posts_per_day: float | None = None
        self.verified_false = False


def _signature(normalized: str) -> str:
    tokens = sorted(set(re.findall(r"[a-z0-9']+", normalized.lower())))[:8]
    return " ".join(tokens) if tokens else normalized[:120]


def build_account_context(records, spam_context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Aggregate all records into bounded per-author state in a single pass."""
    groups: dict[str, _AccountState] = {}
    signature_authors: dict[str, set[str]] = {}

    for idx, record in enumerate(records):
        author = str(record.get("author") or f"anon-{record.get('id', idx)}")
        state = groups.get(author)
        if state is None:
            state = groups[author] = _AccountState()

        normalized = normalize_text(str(record.get("text") or ""))
        signature = _signature(normalized)
        state.posts += 1
        if len(state.unique) < 1000:
            state.unique.add(normalized)
        else:
            state.unique_capped = True
        state.signatures[signature] += 1
        authors = signature_authors.setdefault(signature, set())
        if len(authors) < 500:
            authors.add(author)

        parsed = _parse_time(record.get("timestamp"))
        if parsed is not None and len(state.times) < 200:
            state.times.append(parsed)

        meta = record.get("metadata") or {}
        if any(k in meta for k in ("account_age_days", "followers", "following", "posts_per_day", "verified")):
            state.metadata_available = True
        try:
            if float(meta.get("account_age_days", 9999)) < 10:
                state.meta_signals.add("very new account")
        except (TypeError, ValueError):
            pass
        if meta.get("verified") is False:
            state.verified_false = True
        if meta.get("posts_per_day") is not None:
            try:
                rate = float(meta["posts_per_day"])
                state.max_posts_per_day = max(state.max_posts_per_day or 0.0, rate)
                if rate > 25:
                    state.meta_signals.add("very high posting rate")
            except (TypeError, ValueError):
                pass

    cross_signatures = {sig for sig, authors in signature_authors.items() if len(authors) > 1}
    return {"groups": groups, "cross_signatures": cross_signatures, "spam_context": spam_context}


def finalize_accounts(context: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Turn bounded account state into the same verdict shape as detect_bots()."""
    groups: dict[str, _AccountState] = context["groups"]
    cross_signatures: set[str] = context["cross_signatures"]
    drafts: list[tuple[dict[str, Any], _AccountState]] = []

    for author, state in groups.items():
        posts = max(state.posts, 1)
        unique_ratio = len(state.unique) / posts
        if state.unique_capped:
            unique_ratio = min(1.0, unique_ratio + 0.01)

        times = sorted(state.times)
        intervals = [
            (b - a).total_seconds() / 60
            for a, b in zip(times, times[1:])
        ]
        positive_intervals = [i for i in intervals if i > 0]
        interval_cv = (
            statistics.pstdev(positive_intervals) / statistics.fmean(positive_intervals)
            if len(positive_intervals) >= 4 and statistics.fmean(positive_intervals) > 0
            else None
        )
        span_hours = (times[-1] - times[0]).total_seconds() / 3600 if len(times) >= 2 else 0
        rate = state.posts / span_hours if span_hours > 0 else None
        own_similarity = 1 - unique_ratio if state.posts >= 4 else None
        coordination = sum(
            count for signature, count in state.signatures.items() if signature in cross_signatures
        )

        indicators: list[dict[str, Any]] = []
        if state.posts >= 5 and unique_ratio < 0.55:
            indicators.append({"name": "Repeated content", "detail": f"Only {unique_ratio:.0%} of posts are unique.", "weight": 0.30})
        if interval_cv is not None and interval_cv < 0.20:
            indicators.append({"name": "Regular posting intervals", "detail": f"Interval variation (CV) {interval_cv:.2f} across {len(positive_intervals)} gaps.", "weight": 0.26})
        if rate is not None and rate > 8:
            indicators.append({"name": "High posting frequency", "detail": f"Approximately {rate:.1f} posts/hour over the observed window.", "weight": 0.22})
        if own_similarity is not None and own_similarity > 0.62:
            indicators.append({"name": "Self-similar posts", "detail": f"Estimated content overlap {own_similarity:.2f}.", "weight": 0.24})
        if coordination >= 2:
            indicators.append({"name": "Cross-account coordination", "detail": f"{coordination} post(s) closely mirror posts from other accounts.", "weight": 0.28})
        if "very new account" in state.meta_signals and state.posts >= 5:
            indicators.append({"name": "New account with high volume", "detail": "Account age under 10 days with substantial posting volume.", "weight": 0.18})
        if "very high posting rate" in state.meta_signals:
            indicators.append({"name": "Metadata posting anomaly", "detail": "Declared posts/day is unusually high.", "weight": 0.20})

        summary_bits = [f"{state.posts} posts", f"unique content {unique_ratio:.0%}"]
        if interval_cv is not None:
            summary_bits.append(f"timing consistency {interval_cv:.2f} variation")
        if own_similarity is not None:
            summary_bits.append(f"content similarity {own_similarity:.2f}")
        if coordination:
            summary_bits.append(f"{coordination} cross-account matches")
        summary = "; ".join(summary_bits)

        preliminary_score = sum(i["weight"] for i in indicators)
        draft = {
            "author": author,
            "posts": state.posts,
            "indicators": indicators,
            "summary": summary,
            "unique_ratio": unique_ratio,
            "interval_cv": interval_cv,
            "rate": rate,
            "own_similarity": own_similarity,
            "coordination": coordination,
            "metadata_available": state.metadata_available,
            "meta_signals": sorted(state.meta_signals),
            "preliminary_score": preliminary_score,
        }
        drafts.append((draft, state))

    drafts.sort(key=lambda item: (-(item[0]["preliminary_score"] + 0.05 * item[0]["posts"]), item[0]["author"]))
    nli_by_author: dict[str, dict[str, float] | None] = {}
    for draft, _ in drafts[: config.MAX_NLI_ACCOUNTS]:
        if draft["posts"] >= 3 or draft["metadata_available"]:
            nli_by_author[draft["author"]] = _nli_account(draft["summary"])

    account_summaries: list[dict[str, Any]] = []
    automation_by_author: dict[str, dict[str, Any]] = {}
    for draft, state in drafts:
        author = draft["author"]
        indicators = draft["indicators"]
        nli = nli_by_author.get(author)
        nli_component = 0.18 * clamp((nli["bot"] - nli["human"]) + 0.5) if nli else 0.0
        if nli and nli["bot"] > 0.55:
            indicators.append({
                "name": "Behaviour model signal",
                "detail": f"Account summary scored {nli['bot']:.0%} bot-like by NLI model.",
                "weight": 0.16,
            })
        score = round(clamp(sum(i["weight"] for i in indicators) + nli_component), 4)
        evidence_count = len({i["name"] for i in indicators})

        if draft["posts"] < 3 and not draft["metadata_available"]:
            label = "Insufficient Data"
            note = "Fewer than 3 posts and no account metadata."
        elif score >= 0.72 and evidence_count >= 3:
            label = "Strong Automation Indicators"
            note = "Multiple independent behavioural signals agree."
        elif (score >= 0.40 and evidence_count >= 2) or (score >= 0.50 and evidence_count == 1):
            label = "Possibly Automated"
            note = "Based on multiple signals." if evidence_count >= 2 else "Only one strong signal; confidence is low."
        else:
            label = "Likely Human"
            note = "No sufficient automation pattern in available data."

        uncertainty = 0.18 + (0.20 if draft["posts"] < 5 else 0) + (
            0.18 if not draft["metadata_available"] else 0
        ) + (0.14 if nli is None else 0)
        if evidence_count == 1:
            uncertainty += 0.20

        account = {
            "author": author,
            "posts": draft["posts"],
            "label": label,
            "score": score,
            "confidence": round(clamp(1 - min(uncertainty, 0.85)), 3),
            "uncertainty": round(clamp(uncertainty), 3),
            "note": note,
            "indicators": indicators,
            "signals": {
                "unique_content_ratio": round(draft["unique_ratio"], 3),
                "interval_cv": round(draft["interval_cv"], 3) if draft["interval_cv"] is not None else None,
                "posts_per_hour": round(draft["rate"], 2) if draft["rate"] is not None else None,
                "mean_self_similarity": round(draft["own_similarity"], 3) if draft["own_similarity"] is not None else None,
                "cross_account_matches": draft["coordination"],
                "metadata_available": draft["metadata_available"],
                "metadata_signals": draft["meta_signals"],
            },
        }
        record_info = {
            "label": label,
            "score": score,
            "indicators": indicators,
            "author": author,
            "note": note,
        }
        account_summaries.append(account)
        automation_by_author[author] = record_info

    account_summaries.sort(key=lambda a: (-a["score"], a["author"]))
    return automation_by_author, account_summaries
