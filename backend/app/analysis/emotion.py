"""Emotion detection mapped from GoEmotions onto the ten product-facing labels."""

from __future__ import annotations

import re
from typing import Any

from .. import config, models
from ..utils import clamp

EMOTIONS = [
    "happiness", "anger", "sadness", "frustration", "fear",
    "surprise", "disappointment", "excitement", "trust", "confusion",
]

# GoEmotions labels are grouped; several source labels intentionally contribute
# to more than one target where human annotation is genuinely ambiguous.
GROUP_MAP: dict[str, list[tuple[str, float]]] = {
    "admiration": [("happiness", 0.7), ("trust", 0.3)],
    "amusement": [("happiness", 0.9), ("excitement", 0.1)],
    "anger": [("anger", 0.9), ("frustration", 0.1)],
    "annoyance": [("frustration", 0.7), ("anger", 0.3)],
    "approval": [("trust", 0.6), ("happiness", 0.4)],
    "caring": [("trust", 0.7), ("happiness", 0.3)],
    "confusion": [("confusion", 0.9), ("surprise", 0.1)],
    "curiosity": [("confusion", 0.4), ("surprise", 0.6)],
    "desire": [("excitement", 0.6), ("happiness", 0.4)],
    "disappointment": [("disappointment", 0.9), ("sadness", 0.1)],
    "disapproval": [("frustration", 0.6), ("anger", 0.2), ("disappointment", 0.2)],
    "disgust": [("anger", 0.6), ("frustration", 0.4)],
    "embarrassment": [("sadness", 0.6), ("fear", 0.4)],
    "excitement": [("excitement", 0.9), ("happiness", 0.1)],
    "fear": [("fear", 0.9), ("surprise", 0.1)],
    "frustration": [("frustration", 0.9), ("anger", 0.1)],
    "gratitude": [("trust", 0.7), ("happiness", 0.3)],
    "grief": [("sadness", 0.9), ("disappointment", 0.1)],
    "joy": [("happiness", 0.9), ("excitement", 0.1)],
    "love": [("happiness", 0.7), ("trust", 0.3)],
    "nervousness": [("fear", 0.8), ("confusion", 0.2)],
    "optimism": [("happiness", 0.5), ("excitement", 0.3), ("trust", 0.2)],
    "pride": [("happiness", 0.7), ("trust", 0.3)],
    "remorse": [("sadness", 0.6), ("disappointment", 0.4)],
    "sadness": [("sadness", 0.9), ("disappointment", 0.1)],
    "surprise": [("surprise", 0.8), ("confusion", 0.2)],
    "trust": [("trust", 0.9), ("happiness", 0.1)],
    "neutral": [],
}

LEXICON: dict[str, set[str]] = {
    "happiness": {"happy", "great", "love", "excellent", "good", "wonderful", "pleased", "satisfied"},
    "anger": {"angry", "furious", "outrageous", "unacceptable", "ridiculous", "infuriating"},
    "sadness": {"sad", "heartbroken", "gutted", "upset", "mourn", "miss"},
    "frustration": {"frustrated", "annoyed", "irritating", "tedious", "stuck", "again"},
    "fear": {"afraid", "scared", "worried", "concerned", "nervous", "risk"},
    "surprise": {"surprised", "wow", "unexpected", "shocked", "amazed"},
    "disappointment": {"disappointed", "letdown", "poor", "underwhelming", "expected more"},
    "excitement": {"excited", "cant wait", "can't wait", "thrilled", "awesome", "amazing"},
    "trust": {"trust", "reliable", "recommend", "confident", "honest", "dependable"},
    "confusion": {"confused", "unclear", "confusing", "unsure", "what", "how"},
}


def _normalise(raw: str) -> str:
    cleaned = re.sub(r"[^a-z]", "", str(raw or "").lower())
    return cleaned


def _group_scores(raw_scores: Any) -> dict[str, float]:
    scores = {e: 0.0 for e in EMOTIONS}
    if isinstance(raw_scores, dict) and isinstance(raw_scores.get("labels"), list):
        pairs = zip(raw_scores["labels"], raw_scores["scores"])
    elif isinstance(raw_scores, list):
        pairs = [
            (item.get("label", ""), item.get("score", 0.0))
            for item in raw_scores
            if isinstance(item, dict)
        ]
    else:
        pairs = []

    for label, score in pairs:
        key = _normalise(label)
        if key in GROUP_MAP:
            for target, weight in GROUP_MAP[key]:
                scores[target] += float(score or 0.0) * weight
        elif key in scores:
            scores[key] += float(score or 0.0)
    return scores


def _fallback(text: str) -> dict[str, float]:
    lower = f" {str(text).lower()} "
    scores = {e: 0.0 for e in EMOTIONS}
    for emotion, words in LEXICON.items():
        scores[emotion] = sum(1.0 for word in words if word in lower)
    if not any(scores.values()):
        scores["happiness"] = 0.2
        scores["confusion"] = 0.1
    return scores


def analyze_emotions(texts: list[str]) -> list[dict[str, Any]]:
    """Return the dominant emotion, confidence and a full ten-label distribution."""
    if not texts:
        return []

    raw: list[dict[str, float]] | None = None
    engine = "fallback"
    try:
        pipe = models.emotion_pipeline()
        outputs = pipe(
            texts,
            batch_size=config.BATCH_SIZE,
            top_k=None,
            truncation=True,
            max_length=512,
        )
        if len(outputs) != len(texts):
            outputs = [outputs] * len(texts)
        raw = [_group_scores(output) for output in outputs]
        engine = "huggingface"
    except Exception:
        raw = None

    results: list[dict[str, Any]] = []
    for idx, text in enumerate(texts):
        scores = raw[idx] if raw is not None else _fallback(text)
        total = sum(scores.values())
        if total <= 0:
            scores = {e: 0.0 for e in EMOTIONS}
            scores["happiness"] = 1.0
            total = 1.0
        probabilities = {e: clamp(v / total) for e, v in scores.items()}
        dominant = max(EMOTIONS, key=lambda e: probabilities[e])
        results.append(
            {
                "emotion": dominant,
                "confidence": round(clamp(probabilities[dominant]), 4),
                "probabilities": {k: round(v, 4) for k, v in probabilities.items()},
                "engine": engine,
            }
        )
    return results
