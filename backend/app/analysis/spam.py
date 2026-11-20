"""Suspicious-content detection.

Wording alone is never enough to call a review fake.  The score combines
duplicate/burst patterns, account metadata and an NLI model, then explicitly
caps the verdict when behavioural evidence is unavailable.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .. import config, models
from ..utils import clamp, normalize_text

PROMO_RE = re.compile(
    r"\b(buy now|limited time|discount|promo(?:tion)?|coupon|click (?:here|link)|"
    r"visit (?:my|our)|follow me|check (?:out|my)|free shipping|giveaway|"
    r"order now|best price|lowest price|guaranteed|earn money|dm me|link in bio)\b",
    re.I,
)
URL_RE = re.compile(r"https?://|www\.", re.I)
GENERIC_RE = re.compile(
    r"\b(nice product|good product|great product|good service|nice service|"
    r"very good|good quality|nice one|thanks|ok|okay|recommended|works well|"
    r"best ever|love it|so good)\b",
    re.I,
)
STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "is", "are", "was", "were", "this", "that",
    "it", "i", "my", "me", "we", "you", "your", "for", "to", "of", "in", "on", "with",
    "very", "really", "so", "just", "have", "has", "had", "do", "did", "not", "get",
    "got", "at", "be", "been", "from", "they", "them", "there", "what", "when",
}


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9#']+", text.lower()) if t not in STOPWORDS and len(t) > 1]


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        raw = str(value).strip().replace("Z", "+00:00")
        return datetime.fromisoformat(raw)
    except ValueError:
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(str(value)[:19], fmt)
            except ValueError:
                continue
    return None


def _near_duplicates(texts: list[str]) -> list[float]:
    """Highest cosine similarity to any other item (0 when n < 2)."""
    if len(texts) < 2:
        return [0.0] * len(texts)
    try:
        matrix = TfidfVectorizer(
            ngram_range=(1, 2), min_df=1, sublinear_tf=True, max_features=30000
        ).fit_transform(texts)
        max_sims = np.zeros(len(texts), dtype=float)
        chunk = 256
        for start in range(0, len(texts), chunk):
            block = cosine_similarity(matrix[start:start + chunk], matrix)
            np.fill_diagonal(block[:, start:start + chunk], 0.0)
            max_sims[start:start + chunk] = block.max(axis=1)
        return [float(v) for v in max_sims]
    except Exception:
        return [0.0] * len(texts)


def _nli_scores(texts: list[str]) -> list[dict[str, float] | None]:
    """Zero-shot evidence for a bounded, deterministic subset of records."""
    if not texts:
        return [None] * len(texts)
    limit = min(len(texts), 350)
    candidate_idx = list(range(min(len(texts), 175)))
    if len(texts) > 175:
        # Prioritise texts with obvious promotional language, then the tail.
        ranked = sorted(
            range(len(texts)),
            key=lambda i: (bool(PROMO_RE.search(texts[i])), bool(URL_RE.search(texts[i]))),
            reverse=True,
        )
        for i in ranked:
            if i not in candidate_idx and len(candidate_idx) < limit:
                candidate_idx.append(i)
    scores: list[dict[str, float] | None] = [None] * len(texts)
    labels = ["a genuine personal review", "promotional spam or advertising",
              "generic irrelevant filler", "duplicated repetitive text"]
    try:
        pipe = models.nli_pipeline()
        subset = [texts[i][:512] for i in candidate_idx]
        outputs = pipe(
            subset,
            candidate_labels=labels,
            hypothesis_template="This customer review is {}.",
            batch_size=config.BATCH_SIZE,
            truncation=True,
            max_length=512,
        )
        if isinstance(outputs, dict):
            outputs = [outputs]
        for i, output in zip(candidate_idx, outputs):
            mapping = {
                str(label).lower(): float(score)
                for label, score in zip(output.get("labels", []), output.get("scores", []))
            }
            scores[i] = {
                "genuine": mapping.get(labels[0], 0.0),
                "promo": mapping.get(labels[1], 0.0),
                "generic": mapping.get(labels[2], 0.0),
                "duplicate": mapping.get(labels[3], 0.0),
            }
    except Exception:
        pass
    return scores


def classify_spam(records: list[dict[str, Any]], texts: list[str]) -> list[dict[str, Any]]:
    """Return suspicion scores, labels, explanations and uncertainty."""
    if not records:
        return []

    normalized = [normalize_text(t) for t in texts]
    dup_counts = Counter(normalized)
    near_sims = _near_duplicates([n or "empty" for n in normalized])
    nli = _nli_scores(texts)

    burst_counts: Counter = Counter()
    parsed_times = [_parse_time(r.get("timestamp")) for r in records]
    for text, ts in zip(normalized, parsed_times):
        if ts is not None:
            bucket = ts.strftime("%Y-%m-%dT%H")
            burst_counts[(text, bucket)] += 1

    results: list[dict[str, Any]] = []
    for idx, (record, text, norm) in enumerate(zip(records, texts, normalized)):
        toks = _tokens(norm)
        token_count = max(len(toks), 1)
        top_repeat = max((Counter(toks).values()), default=0) / token_count
        bigrams = Counter(zip(toks, toks[1:]))
        bigram_repeat = max(bigrams.values(), default=0) / max(len(toks) - 1, 1)

        promo_hits = len(PROMO_RE.findall(text))
        url_hit = bool(URL_RE.search(text))
        generic = bool(GENERIC_RE.search(text)) and len(text) < 90
        exact_dup = dup_counts[norm] > 1
        near_dup = near_sims[idx] >= 0.90
        burst = burst_counts.get((norm, parsed_times[idx].strftime("%Y-%m-%dT%H")), 0) >= 3 if parsed_times[idx] else False

        meta = record.get("metadata") or {}
        meta_signals: list[str] = []
        try:
            age = float(meta.get("account_age_days", 9999))
            if age < 7:
                meta_signals.append("very new account")
                meta["_age_flag"] = True
        except (TypeError, ValueError):
            pass
        followers = meta.get("followers")
        following = meta.get("following")
        if followers is not None and following is not None:
            try:
                f, g = max(float(followers), 0), max(float(following), 0)
                if g > 0 and f / g < 0.02:
                    meta_signals.append("abnormal follower/following ratio")
                    meta["_ratio_flag"] = True
            except (TypeError, ValueError):
                pass
        if meta.get("posts_per_day") is not None:
            try:
                if float(meta["posts_per_day"]) > 30:
                    meta_signals.append("very high posting rate")
                    meta["_rate_flag"] = True
            except (TypeError, ValueError):
                pass

        reasons: list[str] = []
        score = 0.0
        behavioural = False

        if exact_dup:
            score += 0.24
            behavioural = True
            reasons.append(f"Exact duplicate text appears {dup_counts[norm]} times in this dataset.")
        if near_dup:
            score += 0.20
            behavioural = True
            reasons.append(f"Near-duplicate wording detected (similarity {near_sims[idx]:.2f}).")
        if burst:
            score += 0.18
            behavioural = True
            reasons.append("Several near-identical posts appeared within the same hour.")
        if meta_signals:
            score += min(0.24, 0.09 * len(meta_signals))
            behavioural = True
            reasons.append("Account metadata: " + ", ".join(meta_signals) + ".")
        if promo_hits:
            score += min(0.22, 0.08 * promo_hits)
            reasons.append(f"Promotional phrasing detected ({promo_hits} phrase(s)).")
        if url_hit:
            score += 0.06
            reasons.append("Contains an outbound link.")
        if top_repeat > 0.18 or bigram_repeat > 0.22:
            repeat_component = min(0.16, max(top_repeat - 0.18, bigram_repeat - 0.22) * 0.8)
            score += repeat_component
            reasons.append("Unusually high word or phrase repetition.")
        if generic:
            score += 0.08
            reasons.append("Very short, generic wording with little specific detail.")

        nli_item = nli[idx]
        if nli_item:
            nli_component = 0.22 * clamp(
                nli_item["promo"] + nli_item["generic"] + nli_item["duplicate"] * 0.7 - nli_item["genuine"] * 0.5
            )
            score += nli_component
            if nli_component > 0.06:
                reasons.append("NLI model found wording similar to advertising or generic filler.")
        else:
            reasons.append("NLI check not run for this record (batch limit); lexical signals only.")

        metadata_available = any(
            k in meta for k in ("account_age_days", "followers", "following", "posts_per_day", "verified")
        )
        if not behavioural:
            score = min(score, 0.56)
            reasons.append(
                "No behavioural or account-level evidence was available; wording alone cannot establish a fake review."
            )

        score = round(clamp(score), 4)
        if score >= 0.68 and behavioural:
            label = "Likely Spam"
        elif score >= 0.34:
            label = "Potentially Suspicious"
        else:
            label = "Likely Genuine"

        uncertainty = 0.20
        if not metadata_available:
            uncertainty += 0.22
        if not behavioural:
            uncertainty += 0.18
        if nli_item is None:
            uncertainty += 0.08
        if len(text) < 40:
            uncertainty += 0.10
        uncertainty = round(clamp(uncertainty), 3)

        if not reasons:
            reasons.append("No suspicious patterns detected in available text or metadata.")

        results.append(
            {
                "label": label,
                "suspicion_score": score,
                "confidence": round(clamp(1 - uncertainty), 3),
                "uncertainty": uncertainty,
                "reasons": reasons[:6],
                "evidence": {
                    "exact_duplicate": exact_dup,
                    "near_duplicate": round(near_sims[idx], 3),
                    "burst": burst,
                    "promotional_phrases": promo_hits,
                    "repetition_ratio": round(top_repeat, 3),
                    "metadata_signals": meta_signals,
                    "nli_evaluated": nli_item is not None,
                },
                "engine": "huggingface+nli" if nli_item else "lexical+behavioral",
            }
        )
    return results


# ---------------------------------------------------------------------------
# Streaming context used by the large-dataset pipeline.  The expensive global
# signals are computed in one pass; classify_record() is then O(1) per row.
# ---------------------------------------------------------------------------


def _near_signature(normalized: str) -> str:
    tokens = sorted(set(_tokens(normalized)))
    if len(tokens) < 2:
        return normalized[:120]
    return " ".join(tokens[:8])


def build_spam_context(records) -> dict[str, Any]:
    """One-pass duplicate/burst counts plus a bounded NLI candidate set."""
    dup_counts: Counter = Counter()
    near_counts: Counter = Counter()
    burst_counts: Counter = Counter()
    priority_candidates: list[tuple[int, int, str]] = []
    first_candidates: list[tuple[int, int, str]] = []
    total = 0

    for idx, record in enumerate(records):
        text = str(record.get("text") or "")
        norm = normalize_text(text)
        dup_counts[norm] += 1
        near_counts[_near_signature(norm)] += 1
        parsed = _parse_time(record.get("timestamp"))
        if parsed is not None:
            burst_counts[(norm, parsed.strftime("%Y-%m-%dT%H"))] += 1

        candidate = (idx, text)
        if PROMO_RE.search(text) or URL_RE.search(text):
            priority_candidates.append((1, idx, text))
        elif idx < 175:
            first_candidates.append((0, idx, text))
        total += 1

    selected = first_candidates + sorted(priority_candidates, key=lambda x: (-x[0], x[1]))[: max(0, 350 - len(first_candidates))]
    selected = sorted(selected, key=lambda x: x[1])[:350]
    nli_scores: dict[int, dict[str, float] | None] = {}
    if selected:
        scores = _nli_scores([text for _, _, text in selected])
        nli_scores = {idx: score for (_, idx, _), score in zip(selected, scores)}

    return {
        "dup_counts": dup_counts,
        "near_counts": near_counts,
        "burst_counts": burst_counts,
        "nli": nli_scores,
        "total": total,
    }


def classify_record(record: dict[str, Any], idx: int, context: dict[str, Any]) -> dict[str, Any]:
    """Classify one row using the pre-computed global spam context."""
    text = str(record.get("text") or "")
    norm = normalize_text(text)
    signature = _near_signature(norm)
    dup_count = context["dup_counts"].get(norm, 0)
    near_count = context["near_counts"].get(signature, 0)
    exact_dup = dup_count > 1
    near_dup = (not exact_dup) and near_count > 1
    near_sim = 0.91 if near_dup else 0.0

    parsed = _parse_time(record.get("timestamp"))
    burst = bool(
        parsed and context["burst_counts"].get((norm, parsed.strftime("%Y-%m-%dT%H")), 0) >= 3
    )

    toks = _tokens(norm)
    token_count = max(len(toks), 1)
    top_repeat = max(Counter(toks).values(), default=0) / token_count
    bigrams = Counter(zip(toks, toks[1:]))
    bigram_repeat = max(bigrams.values(), default=0) / max(len(toks) - 1, 1)

    promo_hits = len(PROMO_RE.findall(text))
    url_hit = bool(URL_RE.search(text))
    generic = bool(GENERIC_RE.search(text)) and len(text) < 90

    meta = record.get("metadata") or {}
    meta_signals: list[str] = []
    try:
        if float(meta.get("account_age_days", 9999)) < 7:
            meta_signals.append("very new account")
    except (TypeError, ValueError):
        pass
    if meta.get("followers") is not None and meta.get("following") is not None:
        try:
            followers = max(float(meta["followers"]), 0)
            following = max(float(meta["following"]), 0)
            if following > 0 and followers / following < 0.02:
                meta_signals.append("abnormal follower/following ratio")
        except (TypeError, ValueError):
            pass
    if meta.get("posts_per_day") is not None:
        try:
            if float(meta["posts_per_day"]) > 30:
                meta_signals.append("very high posting rate")
        except (TypeError, ValueError):
            pass

    metadata_available = any(
        k in meta for k in ("account_age_days", "followers", "following", "posts_per_day", "verified")
    )
    reasons: list[str] = []
    score = 0.0
    behavioural = False

    if exact_dup:
        score += 0.24
        behavioural = True
        reasons.append(f"Exact duplicate text appears {dup_count} times in this dataset.")
    if near_dup:
        score += 0.20
        behavioural = True
        reasons.append(f"Near-duplicate wording detected (similarity {near_sim:.2f}).")
    if burst:
        score += 0.18
        behavioural = True
        reasons.append("Several near-identical posts appeared within the same hour.")
    if meta_signals:
        score += min(0.24, 0.09 * len(meta_signals))
        behavioural = True
        reasons.append("Account metadata: " + ", ".join(meta_signals) + ".")
    if promo_hits:
        score += min(0.22, 0.08 * promo_hits)
        reasons.append(f"Promotional phrasing detected ({promo_hits} phrase(s)).")
    if url_hit:
        score += 0.06
        reasons.append("Contains an outbound link.")
    if top_repeat > 0.18 or bigram_repeat > 0.22:
        repeat_component = min(0.16, max(top_repeat - 0.18, bigram_repeat - 0.22) * 0.8)
        score += repeat_component
        reasons.append("Unusually high word or phrase repetition.")
    if generic:
        score += 0.08
        reasons.append("Very short, generic wording with little specific detail.")

    nli_item = context["nli"].get(idx)
    if nli_item:
        nli_component = 0.22 * clamp(
            nli_item["promo"] + nli_item["generic"] + nli_item["duplicate"] * 0.7 - nli_item["genuine"] * 0.5
        )
        score += nli_component
        if nli_component > 0.06:
            reasons.append("NLI model found wording similar to advertising or generic filler.")
    else:
        reasons.append("NLI check not run for this record (batch limit); lexical signals only.")

    if not behavioural:
        score = min(score, 0.56)
        reasons.append(
            "No behavioural or account-level evidence was available; wording alone cannot establish a fake review."
        )

    score = round(clamp(score), 4)
    if score >= 0.68 and behavioural:
        label = "Likely Spam"
    elif score >= 0.34:
        label = "Potentially Suspicious"
    else:
        label = "Likely Genuine"

    uncertainty = 0.20
    if not metadata_available:
        uncertainty += 0.22
    if not behavioural:
        uncertainty += 0.18
    if nli_item is None:
        uncertainty += 0.08
    if len(text) < 40:
        uncertainty += 0.10
    uncertainty = round(clamp(uncertainty), 3)
    if not reasons:
        reasons.append("No suspicious patterns detected in available text or metadata.")

    return {
        "label": label,
        "suspicion_score": score,
        "confidence": round(clamp(1 - uncertainty), 3),
        "uncertainty": uncertainty,
        "reasons": reasons[:6],
        "evidence": {
            "exact_duplicate": exact_dup,
            "near_duplicate": round(near_sim, 3),
            "burst": burst,
            "promotional_phrases": promo_hits,
            "repetition_ratio": round(top_repeat, 3),
            "metadata_signals": meta_signals,
            "nli_evaluated": nli_item is not None,
        },
        "engine": "huggingface+nli" if nli_item else "lexical+behavioral",
    }
