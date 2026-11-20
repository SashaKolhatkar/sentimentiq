"""Time-series aggregation and alert generation."""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from ..utils import truncate


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    raw = str(value).strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
        return dt.replace(tzinfo=dt.tzinfo or timezone.utc).astimezone(timezone.utc)
    except ValueError:
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d"):
            try:
                return datetime.strptime(raw[:19], fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return None


def _bucket(dt: datetime, period: str) -> str:
    if period == "weekly":
        monday = dt - timedelta(days=dt.weekday())
        return monday.date().isoformat()
    if period == "monthly":
        return dt.strftime("%Y-%m")
    return dt.date().isoformat()


def analyze_trends(
    records: list[dict[str, Any]],
    sentiments: list[str],
    emotions: list[str],
    period: str = "daily",
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    """Aggregate real timestamps; never fabricate a timeline when dates are absent."""
    parsed: list[tuple[datetime, int]] = []
    for idx, record in enumerate(records):
        dt = _parse_time(record.get("timestamp"))
        if dt:
            parsed.append((dt, idx))

    if not parsed:
        return {
            "available": False,
            "message": "No valid timestamps were found. Add a timestamp/date column to enable trend analysis.",
            "series": [],
            "alerts": [],
            "period": period,
        }

    start_dt = _parse_time(start) if start else None
    end_dt = _parse_time(end) if end else None
    if end_dt:
        end_dt = end_dt.replace(hour=23, minute=59, second=59)
    if start_dt:
        parsed = [(dt, i) for dt, i in parsed if dt >= start_dt]
    if end_dt:
        parsed = [(dt, i) for dt, i in parsed if dt <= end_dt]

    if not parsed:
        return {
            "available": False,
            "message": "No records fall inside the selected date range.",
            "series": [],
            "alerts": [],
            "period": period,
        }

    buckets: dict[str, list[int]] = defaultdict(list)
    for dt, idx in parsed:
        buckets[_bucket(dt, period)].append(idx)

    series: list[dict[str, Any]] = []
    for label in sorted(buckets):
        indices = buckets[label]
        counts = Counter(sentiments[i] for i in indices)
        total = len(indices)
        emo_counts = Counter(emotions[i] for i in indices)
        score_sum = 0.0
        for i in indices:
            score_sum += (counts["positive"] - counts["negative"]) / max(total, 1)
        series.append(
            {
                "date": label,
                "total": total,
                "positive": counts["positive"],
                "negative": counts["negative"],
                "neutral": counts["neutral"],
                "mixed": counts["mixed"],
                "positive_rate": round(counts["positive"] / total, 3),
                "negative_rate": round(counts["negative"] / total, 3),
                "satisfaction": round((counts["positive"] + 0.5 * counts["neutral"]) / total, 3),
                "dominant_emotion": emo_counts.most_common(1)[0][0] if emo_counts else "neutral",
                "topics": [],
            }
        )

    alerts: list[dict[str, Any]] = []
    totals = [p["total"] for p in series]
    if len(totals) >= 5:
        mean = statistics.fmean(totals)
        std = statistics.pstdev(totals)
        if std > 0:
            for point in series:
                z = (point["total"] - mean) / std
                if z >= 2:
                    alerts.append(
                        {
                            "type": "discussion_spike",
                            "severity": "high" if z >= 2.5 else "medium",
                            "date": point["date"],
                            "message": f"Discussion volume spiked to {point['total']} items ({z:.1f}σ above average).",
                        }
                    )

    if len(series) >= 2:
        window = max(2, min(3, len(series) // 2))
        recent = series[-window:]
        prior = series[-2 * window:-window] or series[:-window]
        if recent and prior:
            recent_neg = sum(p["negative_rate"] for p in recent) / len(recent)
            prior_neg = sum(p["negative_rate"] for p in prior) / len(prior)
            delta = recent_neg - prior_neg
            if delta >= 0.12:
                alerts.append(
                    {
                        "type": "negative_increase",
                        "severity": "high" if delta >= 0.22 else "medium",
                        "date": recent[-1]["date"],
                        "message": f"Negative sentiment rose {delta * 100:.0f} percentage points versus the previous period.",
                    }
                )
            elif delta <= -0.12:
                alerts.append(
                    {
                        "type": "satisfaction_improving",
                        "severity": "info",
                        "date": recent[-1]["date"],
                        "message": f"Negative sentiment fell {abs(delta) * 100:.0f} percentage points — satisfaction is improving.",
                    }
                )

    return {
        "available": True,
        "period": period,
        "start": min(p["date"] for p in series),
        "end": max(p["date"] for p in series),
        "series": series,
        "alerts": alerts[:12],
        "message": None,
        "sample_examples": [
            truncate(str(r.get("text", "")), 140)
            for r in records[:2]
        ],
    }


class TrendAggregator:
    """Streaming time-series builder with no per-record index arrays."""

    def __init__(self, period: str = "daily", start: str | None = None, end: str | None = None) -> None:
        self.period = period
        self.start_dt = _parse_time(start) if start else None
        self.end_dt = _parse_time(end) if end else None
        if self.end_dt:
            self.end_dt = self.end_dt.replace(hour=23, minute=59, second=59)
        self.buckets: dict[str, dict[str, Any]] = {}
        self.dated_count = 0
        self.sample_examples: list[str] = []

    def add(self, record: dict[str, Any], sentiment: str, emotion: str) -> None:
        if len(self.sample_examples) < 2:
            self.sample_examples.append(truncate(str(record.get("text") or ""), 140))
        dt = _parse_time(record.get("timestamp"))
        if not dt:
            return
        if self.start_dt and dt < self.start_dt:
            return
        if self.end_dt and dt > self.end_dt:
            return
        self.dated_count += 1
        label = _bucket(dt, self.period)
        bucket = self.buckets.setdefault(label, {
            "total": 0, "sentiments": Counter(), "emotions": Counter()
        })
        bucket["total"] += 1
        bucket["sentiments"][sentiment] += 1
        bucket["emotions"][emotion] += 1

    def result(self) -> dict[str, Any]:
        if not self.dated_count:
            message = (
                "No records fall inside the selected date range."
                if (self.start_dt or self.end_dt)
                else "No valid timestamps were found. Add a timestamp/date column to enable trend analysis."
            )
            return {
                "available": False, "message": message, "series": [],
                "alerts": [], "period": self.period,
                "start": self.start_dt.date().isoformat() if self.start_dt else None,
                "end": self.end_dt.date().isoformat() if self.end_dt else None,
                "sample_examples": self.sample_examples,
            }

        series: list[dict[str, Any]] = []
        for label in sorted(self.buckets):
            bucket = self.buckets[label]
            counts = bucket["sentiments"]
            total = max(bucket["total"], 1)
            series.append({
                "date": label,
                "total": bucket["total"],
                "positive": counts["positive"],
                "negative": counts["negative"],
                "neutral": counts["neutral"],
                "mixed": counts["mixed"],
                "positive_rate": round(counts["positive"] / total, 3),
                "negative_rate": round(counts["negative"] / total, 3),
                "satisfaction": round((counts["positive"] + 0.5 * counts["neutral"]) / total, 3),
                "dominant_emotion": bucket["emotions"].most_common(1)[0][0],
                "topics": [],
            })

        alerts: list[dict[str, Any]] = []
        totals = [p["total"] for p in series]
        if len(totals) >= 5:
            mean = statistics.fmean(totals)
            std = statistics.pstdev(totals)
            if std > 0:
                for point in series:
                    z = (point["total"] - mean) / std
                    if z >= 2:
                        alerts.append({
                            "type": "discussion_spike",
                            "severity": "high" if z >= 2.5 else "medium",
                            "date": point["date"],
                            "message": f"Discussion volume spiked to {point['total']} items ({z:.1f}σ above average).",
                        })

        if len(series) >= 2:
            window = max(2, min(3, len(series) // 2))
            recent = series[-window:]
            prior = series[-2 * window:-window] or series[:-window]
            if recent and prior:
                recent_neg = sum(p["negative_rate"] for p in recent) / len(recent)
                prior_neg = sum(p["negative_rate"] for p in prior) / len(prior)
                delta = recent_neg - prior_neg
                if delta >= 0.12:
                    alerts.append({
                        "type": "negative_increase",
                        "severity": "high" if delta >= 0.22 else "medium",
                        "date": recent[-1]["date"],
                        "message": f"Negative sentiment rose {delta * 100:.0f} percentage points versus the previous period.",
                    })
                elif delta <= -0.12:
                    alerts.append({
                        "type": "satisfaction_improving",
                        "severity": "info",
                        "date": recent[-1]["date"],
                        "message": f"Negative sentiment fell {abs(delta) * 100:.0f} percentage points — satisfaction is improving.",
                    })

        return {
            "available": True,
            "period": self.period,
            "start": min(p["date"] for p in series),
            "end": max(p["date"] for p in series),
            "series": series,
            "alerts": alerts[:12],
            "message": None,
            "sample_examples": self.sample_examples,
        }
