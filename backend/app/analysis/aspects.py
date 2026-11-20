"""Aspect-based customer review intelligence."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from .. import config
from .sentiment import analyze_sentiment
from ..utils import split_clauses, truncate

ASPECTS: dict[str, list[str]] = {
    "Product Quality": ["quality", "material", "build", "durable", "sturdy", "finish", "workmanship", "defect", "broken", "faulty"],
    "Pricing": ["price", "pricing", "cost", "value", "expensive", "cheap", "affordable", "worth", "discount", "overpriced"],
    "Customer Service": ["service", "support", "staff", "agent", "team", "response", "responded", "helpful", "rude", "representative"],
    "Delivery": ["delivery", "shipping", "ship", "arrived", "arrival", "late", "fast shipping", "courier", "tracking", "dispatch"],
    "Packaging": ["packaging", "package", "packed", "box", "wrapped", "damaged in transit"],
    "Product Features": ["feature", "features", "function", "functions", "settings", "app", "interface", "battery", "size", "design", "compatibility"],
    "User Experience": ["experience", "easy to use", "easy to setup", "setup", "usability", "comfortable", "intuitive", "confusing", "learning curve"],
    "Reliability": ["reliable", "reliability", "consistent", "depends", "stopped working", "failed", "lasted", "durable", "trust"],
}

SUGGESTION_RE = re.compile(
    r"\b(should|could|wish|hope|please|need(?:s)?|suggest|recommend(?:ed)?|would like|"
    r"improve|better|add|fix|make)\b",
    re.I,
)


def _match_aspects(clause: str) -> list[str]:
    lower = clause.lower()
    return [aspect for aspect, words in ASPECTS.items() if any(w in lower for w in words)]


def analyze_aspects(records: list[dict[str, Any]], texts: list[str]) -> dict[str, Any]:
    """Aggregate aspect sentiment, complaints, praise and suggestions."""
    all_clauses: list[str] = []
    owners: list[int] = []
    clause_aspects: list[list[str]] = []
    for idx, text in enumerate(texts):
        for clause in split_clauses(text):
            aspects = _match_aspects(clause)
            if aspects:
                all_clauses.append(clause)
                owners.append(idx)
                clause_aspects.append(aspects)

    predictions = analyze_sentiment(all_clauses) if all_clauses else []
    stats: dict[str, dict[str, float]] = {
        a: {"positive": 0, "negative": 0, "neutral": 0, "mixed": 0, "total": 0, "score_sum": 0.0}
        for a in ASPECTS
    }
    examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    suggestions: list[dict[str, Any]] = []

    for pos, (clause, owner, aspects, pred) in enumerate(
        zip(all_clauses, owners, clause_aspects, predictions)
    ):
        for aspect in aspects:
            bucket = stats[aspect]
            bucket[pred["sentiment"]] += 1
            bucket["total"] += 1
            bucket["score_sum"] += pred["sentiment_score"]
            if len(examples[aspect]) < 4:
                examples[aspect].append(
                    {
                        "record_id": records[owner].get("id", str(owner)),
                        "text": truncate(clause, 180),
                        "sentiment": pred["sentiment"],
                        "score": pred["sentiment_score"],
                    }
                )

    for idx, text in enumerate(texts):
        if SUGGESTION_RE.search(text):
            aspects = _match_aspects(text) or ["General"]
            for aspect in aspects:
                if len(suggestions) < 40:
                    suggestions.append(
                        {
                            "aspect": aspect,
                            "text": truncate(text, 220),
                            "record_id": records[idx].get("id", str(idx)),
                        }
                    )

    aspect_rows: list[dict[str, Any]] = []
    for aspect, bucket in stats.items():
        total = int(bucket["total"])
        if not total:
            continue
        pos_n = int(bucket["positive"])
        neg_n = int(bucket["negative"])
        aspect_rows.append(
            {
                "aspect": aspect,
                "mentions": total,
                "positive": pos_n,
                "negative": neg_n,
                "neutral": int(bucket["neutral"]),
                "mixed": int(bucket["mixed"]),
                "positive_rate": round(pos_n / total, 3),
                "negative_rate": round(neg_n / total, 3),
                "average_score": round(bucket["score_sum"] / total, 3),
                "dominant_sentiment": max(
                    ("positive", "negative", "neutral", "mixed"),
                    key=lambda k: bucket[k],
                ),
                "examples": examples.get(aspect, []),
            }
        )

    appreciated = sorted(
        [a for a in aspect_rows if a["mentions"] >= 2],
        key=lambda a: (a["positive_rate"], a["mentions"]),
        reverse=True,
    )[:5]
    complaints = sorted(
        [a for a in aspect_rows if a["negative"] >= 1],
        key=lambda a: (a["negative_rate"], a["negative"]),
        reverse=True,
    )[:5]

    return {
        "aspects": sorted(aspect_rows, key=lambda a: -a["mentions"]),
        "most_appreciated": appreciated,
        "top_complaints": complaints,
        "suggestions": suggestions[:25],
        "coverage": {
            "clauses_with_aspects": len(all_clauses),
            "total_records": len(records),
            "engine": "huggingface" if predictions and predictions[0].get("engine") == "huggingface" else "fallback",
        },
    }


class AspectAggregator:
    """Bounded streaming version of analyze_aspects()."""

    def __init__(self, total_records: int) -> None:
        self.total_records = total_records
        self.stats: dict[str, dict[str, float]] = {
            a: {"positive": 0, "negative": 0, "neutral": 0, "mixed": 0, "total": 0, "score_sum": 0.0}
            for a in ASPECTS
        }
        self.examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.suggestions: list[dict[str, Any]] = []
        self.clause_count = 0
        self.engine = "fallback"
        self._buffer: list[tuple[str, str, list[str]]] = []

    def add(self, record: dict[str, Any], text: str) -> None:
        for clause in split_clauses(text):
            matched = _match_aspects(clause)
            if matched:
                self.clause_count += 1
                self._buffer.append((str(record.get("id") or ""), clause, matched))
        if SUGGESTION_RE.search(text) and len(self.suggestions) < 40:
            for aspect in _match_aspects(text) or ["General"]:
                if len(self.suggestions) >= 40:
                    break
                self.suggestions.append({
                    "aspect": aspect,
                    "text": truncate(text, 220),
                    "record_id": str(record.get("id") or ""),
                })
        if len(self._buffer) >= config.INFERENCE_CHUNK:
            self.flush()

    def flush(self) -> None:
        if not self._buffer:
            return
        predictions = analyze_sentiment([clause for _, clause, _ in self._buffer])
        if predictions and predictions[0].get("engine") == "huggingface":
            self.engine = "huggingface"
        for (record_id, clause, aspects), pred in zip(self._buffer, predictions):
            for aspect in aspects:
                bucket = self.stats[aspect]
                bucket[pred["sentiment"]] += 1
                bucket["total"] += 1
                bucket["score_sum"] += pred["sentiment_score"]
                if len(self.examples[aspect]) < 4:
                    self.examples[aspect].append({
                        "record_id": record_id,
                        "text": truncate(clause, 180),
                        "sentiment": pred["sentiment"],
                        "score": pred["sentiment_score"],
                    })
        self._buffer.clear()

    def result(self) -> dict[str, Any]:
        self.flush()
        aspect_rows: list[dict[str, Any]] = []
        for aspect, bucket in self.stats.items():
            total = int(bucket["total"])
            if not total:
                continue
            pos_n = int(bucket["positive"])
            neg_n = int(bucket["negative"])
            aspect_rows.append({
                "aspect": aspect,
                "mentions": total,
                "positive": pos_n,
                "negative": neg_n,
                "neutral": int(bucket["neutral"]),
                "mixed": int(bucket["mixed"]),
                "positive_rate": round(pos_n / total, 3),
                "negative_rate": round(neg_n / total, 3),
                "average_score": round(bucket["score_sum"] / total, 3),
                "dominant_sentiment": max(
                    ("positive", "negative", "neutral", "mixed"), key=lambda k: bucket[k]
                ),
                "examples": self.examples.get(aspect, []),
            })
        appreciated = sorted(
            [a for a in aspect_rows if a["mentions"] >= 2],
            key=lambda a: (a["positive_rate"], a["mentions"]), reverse=True,
        )[:5]
        complaints = sorted(
            [a for a in aspect_rows if a["negative"] >= 1],
            key=lambda a: (a["negative_rate"], a["negative"]), reverse=True,
        )[:5]
        return {
            "aspects": sorted(aspect_rows, key=lambda a: -a["mentions"]),
            "most_appreciated": appreciated,
            "top_complaints": complaints,
            "suggestions": self.suggestions[:25],
            "coverage": {
                "clauses_with_aspects": self.clause_count,
                "total_records": self.total_records,
                "engine": self.engine,
            },
        }
