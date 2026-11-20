"""Analysis orchestration for small and large datasets.

Records are streamed from staged JSONL storage. Global signals (duplicates,
bursts, account aggregates) are computed in bounded passes, then each row is
classified in chunks and appended to a run-level JSONL file. Only summaries are
kept in memory and returned to the browser.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from itertools import islice
from typing import Any, Callable, Iterable, Iterator

from .. import config, store
from ..utils import clamp, new_id, pct, redact_pii, utcnow
from . import aspects as aspect_module
from . import bot as bot_module
from . import emotion as emotion_module
from . import insights as insight_module
from . import sentiment as sentiment_module
from . import spam as spam_module
from . import topics as topic_module
from . import trends as trend_module

Progress = Callable[[int, str], None]


def _noop(*_: Any) -> None:
    return None


def _percentages(counts: Counter, total: int) -> dict[str, float]:
    return {
        key: round(counts.get(key, 0) / max(total, 1) * 100, 1)
        for key in ("positive", "negative", "neutral", "mixed")
    }


def _source_iterator(dataset_id: str | None, source_records: Iterable[dict[str, Any]] | None) -> Iterator[dict[str, Any]]:
    if dataset_id:
        return store.iter_dataset(dataset_id)
    if source_records is not None:
        return iter(source_records)
    raise ValueError("A dataset_id or source_records is required")


def _prepared(
    dataset_id: str | None,
    source_records: Iterable[dict[str, Any]] | None,
    redact: bool,
    limit: int,
    parent_is_demo: bool,
) -> Iterator[dict[str, Any]]:
    for idx, item in enumerate(islice(_source_iterator(dataset_id, source_records), limit)):
        raw_text = str(item.get("text") or "")
        text = redact_pii(raw_text) if redact else raw_text
        yield {
            "id": str(item.get("id") or f"r-{idx + 1}"),
            "text": text,
            "platform": str(item.get("platform") or "unknown"),
            "author": item.get("author"),
            "timestamp": item.get("timestamp"),
            "metadata": item.get("metadata") or {},
            "source_type": item.get("source_type") or "manual",
            "is_demo": bool(item.get("is_demo", parent_is_demo)),
        }


def _bucket_index(score: float, buckets: int) -> int:
    for idx in range(buckets):
        low = -1 + 2 * idx / buckets
        high = -1 + 2 * (idx + 1) / buckets
        if low <= score <= high or (idx == buckets - 1 and score > high):
            return idx
    return buckets - 1


def _score_buckets(counts: list[int], buckets: int = 7) -> list[dict[str, Any]]:
    labels: list[dict[str, Any]] = []
    for idx in range(buckets):
        low = -1 + 2 * idx / buckets
        high = -1 + 2 * (idx + 1) / buckets
        labels.append({
            "range": f"{low:.2f} to {high:.2f}",
            "mid": round((low + high) / 2, 2),
            "count": counts[idx] if idx < len(counts) else 0,
        })
    return labels


def run_analysis(
    name: str,
    source_records: Iterable[dict[str, Any]] | None = None,
    dataset_id: str | None = None,
    options: dict[str, Any] | None = None,
    source_type: str = "manual",
    is_demo: bool = False,
    progress: Progress = _noop,
) -> dict[str, Any]:
    options = options or {}
    redact = bool(options.get("redact_pii", True))
    period = str(options.get("period", "daily"))

    meta = None
    if dataset_id:
        meta = store.dataset_meta(dataset_id)
        if not meta:
            raise FileNotFoundError("Dataset not found or expired")
        source_type = meta.get("source_type") or source_type
        is_demo = bool(meta.get("is_demo", is_demo))
        declared_total = int(meta.get("record_count", 0))
    else:
        declared_total = len(source_records) if source_records is not None and hasattr(source_records, "__len__") else 0

    total = declared_total
    if declared_total <= 0:
        total = config.MAX_RECORDS
    limit = min(total, config.ANALYZE_LIMIT) if config.ANALYZE_LIMIT > 0 else total
    if limit <= 0:
        raise ValueError("At least one record is required")
    notices: list[str] = []
    if declared_total > limit:
        notices.append(
            f"Dataset truncated from {declared_total:,} to {limit:,} records "
            f"(SENTIMENTIQ_ANALYZE_LIMIT={config.ANALYZE_LIMIT})."
        )

    def rows() -> Iterator[dict[str, Any]]:
        return _prepared(dataset_id, source_records, redact, limit, is_demo)

    progress(6, "Computing dataset-wide signals")
    spam_context = spam_module.build_spam_context(rows())
    progress(14, "Aggregating account behaviour")
    bot_context = bot_module.build_account_context(rows(), spam_context)
    automation_by_author, all_accounts = bot_module.finalize_accounts(bot_context)
    account_counts = Counter(a["label"] for a in all_accounts)
    accounts_analysed = len(all_accounts)
    # Full automation is applied to every record, but only a bounded, ranked
    # account list is returned in the run JSON.
    accounts = all_accounts[: config.MAX_ACCOUNT_SUMMARIES]
    if accounts_analysed > len(accounts):
        notices.append(
            f"Account report shows the top {len(accounts):,} of {accounts_analysed:,} accounts; "
            "every record still received its account-level verdict."
        )

    run_id = new_id("run_")
    writer = store.RecordWriter(run_id)
    aspect_agg = aspect_module.AspectAggregator(limit)
    topic_agg = topic_module.TopicAggregator(limit)
    trend_agg = trend_module.TrendAggregator(
        period=period, start=options.get("start"), end=options.get("end")
    )

    sentiment_counts: Counter = Counter()
    emotion_counts: Counter = Counter()
    spam_counts: Counter = Counter()
    platform_map: dict[str, Counter] = defaultdict(Counter)
    engines: set[str] = set()
    sentiment_score_sum = 0.0
    suspicion_sum = 0.0
    emotion_confidence_sum = 0.0
    sentiment_buckets = [0] * 7
    spam_buckets = [0] * 5
    demos = True
    processed = 0
    last_progress = 6

    try:
        progress(20, "Analysing records")
        iterator = rows()
        while True:
            chunk = list(islice(iterator, config.INFERENCE_CHUNK))
            if not chunk:
                break
            texts = [record["text"] for record in chunk]
            sentiments = sentiment_module.analyze_sentiment(texts)
            emotions = emotion_module.analyze_emotions(texts)

            for idx_in_chunk, (record, text) in enumerate(zip(chunk, texts)):
                idx = processed + idx_in_chunk
                sent = sentiments[idx_in_chunk]
                emo = emotions[idx_in_chunk]
                spam_result = spam_module.classify_record(record, idx, spam_context)
                author = str(record.get("author") or f"anon-{record.get('id', idx)}")
                automation = automation_by_author.get(
                    author,
                    {"label": "Insufficient Data", "score": 0.0, "indicators": [],
                     "author": author, "note": "No account summary available."},
                )

                writer.write({
                    **record,
                    "sentiment": sent["sentiment"],
                    "sentiment_score": sent["sentiment_score"],
                    "sentiment_confidence": sent["confidence"],
                    "emotion": emo["emotion"],
                    "emotion_confidence": emo["confidence"],
                    "spam_label": spam_result["label"],
                    "suspicion_score": spam_result["suspicion_score"],
                    "spam_confidence": spam_result["confidence"],
                    "spam_uncertainty": spam_result["uncertainty"],
                    "spam_reasons": spam_result["reasons"],
                    "spam_evidence": spam_result["evidence"],
                    "automation_label": automation["label"],
                    "automation_score": automation["score"],
                    "automation_indicators": automation["indicators"],
                })

                sentiment_label = sent["sentiment"]
                emotion_label = emo["emotion"]
                sentiment_counts[sentiment_label] += 1
                emotion_counts[emotion_label] += 1
                spam_counts[spam_result["label"]] += 1
                platform_map[record["platform"] or "unknown"][sentiment_label] += 1
                engines.update((sent["engine"], emo["engine"], spam_result["engine"]))
                sentiment_score_sum += float(sent["sentiment_score"])
                suspicion_sum += float(spam_result["suspicion_score"])
                emotion_confidence_sum += float(emo["confidence"])
                sentiment_buckets[_bucket_index(float(sent["sentiment_score"]), 7)] += 1
                spam_buckets[min(4, max(0, int(float(spam_result["suspicion_score"]) * 5)))] += 1
                aspect_agg.add(record, text)
                topic_agg.add(idx, text, sentiment_label, record.get("timestamp"), record["platform"])
                trend_agg.add(record, sentiment_label, emotion_label)
                demos = demos and record["is_demo"]

            processed += len(chunk)
            pct_done = min(92, 20 + int(72 * processed / max(limit, 1)))
            if pct_done >= last_progress + 2 or processed >= limit:
                progress(pct_done, f"Analysed {processed:,} of {limit:,} records")
                last_progress = pct_done

        writer.close(commit=True)
    except Exception:
        writer.close(commit=False)
        raise

    progress(95, "Building summary and insights")
    aspect_result = aspect_agg.result()
    topic_result = topic_agg.result()
    trend_result = trend_agg.result()
    analyzed = max(processed, 1)

    platform_sentiment = [
        {
            "platform": platform,
            "total": sum(counts.values()),
            "positive": counts["positive"],
            "negative": counts["negative"],
            "neutral": counts["neutral"],
            "mixed": counts["mixed"],
        }
        for platform, counts in sorted(platform_map.items(), key=lambda kv: -sum(kv[1].values()))
    ]

    average_score = round(sentiment_score_sum / analyzed, 4)
    average_suspicion = round(suspicion_sum / analyzed, 4)
    summary = {
        "total_records": processed,
        "sentiment_counts": dict(sentiment_counts),
        "sentiment_percentages": _percentages(sentiment_counts, processed),
        "average_sentiment_score": average_score,
        "satisfaction_score": round(
            (sentiment_counts["positive"] + 0.5 * sentiment_counts["neutral"]) / analyzed * 100, 1
        ),
        "emotion_counts": dict(emotion_counts),
        "emotion_distribution": [
            {"emotion": key, "count": value, "percentage": round(value / analyzed * 100, 1)}
            for key, value in emotion_counts.most_common()
        ],
        "spam_labels": dict(spam_counts),
        "spam": {
            "labels": dict(spam_counts),
            "suspicious_percentage": pct(
                (spam_counts["Potentially Suspicious"] + spam_counts["Likely Spam"]) / analyzed
            ),
            "flagged_count": spam_counts["Potentially Suspicious"] + spam_counts["Likely Spam"],
            "average_suspicion_score": average_suspicion,
        },
        "bots": {
            "labels": dict(account_counts),
            "accounts_analysed": accounts_analysed,
            "automated_accounts": account_counts["Possibly Automated"] + account_counts["Strong Automation Indicators"],
        },
        "platform_sentiment": platform_sentiment,
        "engines": sorted(engines),
        "redaction_applied": redact,
        "is_demo": is_demo and demos,
        "date_range": {"start": trend_result.get("start"), "end": trend_result.get("end")},
    }

    result: dict[str, Any] = {
        "id": run_id,
        "created_at": utcnow(),
        "name": name or "Untitled analysis",
        "source_type": source_type,
        "is_demo": summary["is_demo"],
        "summary": summary,
        "sentiment": {
            "counts": dict(sentiment_counts),
            "percentages": summary["sentiment_percentages"],
            "average_score": average_score,
            "score_buckets": _score_buckets(sentiment_buckets, 7),
            "mixed_count": sentiment_counts["mixed"],
        },
        "emotions": {
            "counts": dict(emotion_counts),
            "distribution": summary["emotion_distribution"],
            "average_confidence": round(emotion_confidence_sum / analyzed, 3),
        },
        "spam": {
            **summary["spam"],
            "score_buckets": _score_buckets(spam_buckets, 5),
            "warning": "Wording alone is never treated as proof of a fake review. Behavioural evidence is required for a Likely Spam verdict.",
        },
        "bots": {**summary["bots"], "accounts": accounts},
        "aspects": aspect_result,
        "topics": topic_result,
        "trends": trend_result,
        "insights": {},
        "notices": notices,
        "storage": "streaming-jsonl",
    }
    result["insights"] = insight_module.generate_insights(result)
    progress(100, "Analysis complete")
    return result
