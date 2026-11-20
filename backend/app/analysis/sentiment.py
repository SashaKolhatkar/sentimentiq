"""Sentiment classification with the TweetEval-style RoBERTa model.

The model provides positive / neutral / negative probabilities.  ``Mixed`` is
derived from contrast clauses (e.g. "great quality but slow delivery") so the
four requested classes remain meaningful without inventing a fifth model.
"""

from __future__ import annotations

import re
from typing import Any

from .. import config, models
from ..utils import clamp, split_clauses

POSITIVE_WORDS = {
    "good", "great", "excellent", "amazing", "love", "loved", "nice", "perfect",
    "awesome", "fantastic", "helpful", "fast", "quality", "recommend", "happy",
    "satisfied", "worth", "beautiful", "easy", "reliable", "friendly", "best",
    "better", "impressed", "smooth", "delighted", "solid", "clean", "responsive",
}
NEGATIVE_WORDS = {
    "bad", "terrible", "awful", "hate", "poor", "worst", "slow", "broken", "late",
    "delay", "delayed", "problem", "issue", "disappointed", "frustrated", "useless",
    "expensive", "rude", "difficult", "failed", "failure", "damaged", "fake", "scam",
    "worse", "annoying", "missing", "refund", "complaint", "unreliable", "confusing",
}
NEGATORS = {"not", "no", "never", "isn't", "wasn't", "don't", "didn't", "can't", "cannot", "hardly", "barely"}
LABEL_MAP = {
    "positive": "positive", "pos": "positive", "label_2": "positive", "4 stars": "positive", "5 stars": "positive",
    "negative": "negative", "neg": "negative", "label_0": "negative", "1 star": "negative", "2 stars": "negative",
    "neutral": "neutral", "neu": "neutral", "label_1": "neutral", "3 stars": "neutral",
    "mixed": "mixed",
}


def _normalise_label(label: str) -> str:
    key = str(label or "").strip().lower()
    return LABEL_MAP.get(key, key)


def _probabilities(output: Any) -> dict[str, float]:
    """Normalise any HF classification output into a label -> score mapping."""
    probs = {"positive": 0.0, "neutral": 0.0, "negative": 0.0}
    if isinstance(output, dict) and isinstance(output.get("labels"), list):
        pairs = zip(output["labels"], output["scores"])
    elif isinstance(output, list):
        pairs = [
            (item.get("label", ""), item.get("score", 0.0))
            for item in output
            if isinstance(item, dict)
        ]
    elif isinstance(output, dict):
        pairs = [(output.get("label", ""), output.get("score", 0.0))]
    else:
        pairs = []
    for label, score in pairs:
        norm = _normalise_label(label)
        if norm in probs:
            probs[norm] = max(probs[norm], float(score or 0.0))
    total = sum(probs.values())
    if total <= 0:
        probs["neutral"] = 1.0
        return probs
    return {k: v / total for k, v in probs.items()}


def _predict(texts: list[str]) -> tuple[list[dict[str, float]] | None, str]:
    try:
        pipe = models.sentiment_pipeline()
        raw = pipe(
            texts,
            batch_size=config.BATCH_SIZE,
            top_k=None,
            truncation=True,
            max_length=512,
        )
        if len(raw) != len(texts):
            raw = [raw] * len(texts)
        return [_probabilities(item) for item in raw], "huggingface"
    except Exception:
        return None, "fallback"


def _fallback(text: str) -> dict[str, float]:
    tokens = re.findall(r"[a-z']+", str(text).lower())
    pos = neg = 0.0
    for idx, token in enumerate(tokens):
        window = tokens[max(0, idx - 3): idx]
        negated = bool(set(window) & NEGATORS)
        if token in POSITIVE_WORDS:
            pos += -0.75 if negated else 1.0
        if token in NEGATIVE_WORDS:
            neg += -0.75 if negated else 1.0
    if pos == neg:
        return {"positive": 0.15, "neutral": 0.7, "negative": 0.15}
    score = (pos - neg) / max(pos + neg, 1.0)
    return {
        "positive": clamp((score + 1) / 2),
        "negative": clamp((1 - score) / 2),
        "neutral": 0.08,
    }


def _is_mixed(text: str, base: dict[str, float], clause_probs: list[dict[str, float]]) -> bool:
    if len(clause_probs) < 2:
        return False
    has_pos = any(p["positive"] >= 0.62 for p in clause_probs)
    has_neg = any(p["negative"] >= 0.55 for p in clause_probs)
    contrast = bool(
        re.search(r"\b(but|however|though|although|yet|whereas|while|except)\b", text, re.I)
    )
    return contrast and has_pos and has_neg and base["positive"] > 0.2 and base["negative"] > 0.15


def analyze_sentiment(texts: list[str]) -> list[dict[str, Any]]:
    """Return sentiment, calibrated score and class probabilities for each text."""
    if not texts:
        return []

    base_probs, engine = _predict(texts)

    clause_texts: list[str] = []
    clause_owner: list[int] = []
    for idx, text in enumerate(texts):
        clauses = split_clauses(text)
        if len(clauses) > 1:
            for clause in clauses:
                clause_texts.append(clause)
                clause_owner.append(idx)

    clause_probs_all: list[dict[str, float]] = []
    if clause_texts and engine == "huggingface":
        predicted, _ = _predict(clause_texts)
        clause_probs_all = predicted or []
    elif clause_texts:
        clause_probs_all = [_fallback(c) for c in clause_texts]

    results: list[dict[str, Any]] = []
    for idx, text in enumerate(texts):
        probs = (
            base_probs[idx]
            if base_probs is not None
            else _fallback(text)
        )
        # Fallback lexicon probabilities need normalising after the neutral floor.
        total = sum(probs.values()) or 1.0
        probs = {k: v / total for k, v in probs.items()}

        clause_probs = [
            p for p, owner in zip(clause_probs_all, clause_owner) if owner == idx
        ]
        mixed = _is_mixed(text, probs, clause_probs)
        if mixed:
            pos_peak = max((p["positive"] for p in clause_probs), default=0.0)
            neg_peak = max((p["negative"] for p in clause_probs), default=0.0)
            probs = {
                "positive": round(pos_peak * 0.42, 4),
                "negative": round(neg_peak * 0.42, 4),
                "neutral": round(0.06, 4),
                "mixed": round(clamp((pos_peak + neg_peak) / 2), 4),
            }
            label = "mixed"
            confidence = clamp((pos_peak + neg_peak) / 2)
        else:
            label = max(("positive", "neutral", "negative"), key=lambda k: probs[k])
            confidence = probs[label]
            probs["mixed"] = 0.0

        score = round(probs["positive"] - probs["negative"], 4)
        results.append(
            {
                "sentiment": label,
                "sentiment_score": score,
                "confidence": round(clamp(confidence), 4),
                "probabilities": {k: round(v, 4) for k, v in probs.items()},
                "engine": engine,
                "mixed_detected": mixed,
            }
        )
    return results
