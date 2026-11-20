"""Scale smoke test: 100k rows through staging, streaming analysis, paging and CSV/PDF.

Transformer inference is replaced with a deterministic stub here so the test
finishes in seconds. Real-model correctness is covered by smoke_test.py.
Run from the project root with: python smoke_large.py
"""

from __future__ import annotations

import csv
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))

from app import config, db, reports, store  # noqa: E402
from app.analysis import aspects, bot, emotion, pipeline, sentiment, spam, topics  # noqa: E402


def _sentiment(texts: list[str]) -> list[dict]:
    out = []
    for text in texts:
        score = round(((sum(ord(c) for c in text[:24]) % 201) - 100) / 100, 3)
        label = "positive" if score > 0.15 else "negative" if score < -0.15 else "neutral"
        out.append({"sentiment": label, "sentiment_score": score, "confidence": 0.91, "engine": "scale-stub"})
    return out


def _emotion(texts: list[str]) -> list[dict]:
    labels = ["joy", "anger", "neutral", "sadness", "surprise"]
    return [
        {"emotion": labels[i % len(labels)], "confidence": 0.88, "engine": "scale-stub"}
        for i, _ in enumerate(texts)
    ]


def _nli(texts: list[str]) -> list[None]:
    return [None for _ in texts]


def _clusters(texts: list[str], sentiments: list[str]) -> list[dict]:
    return [{"label": "scale-topic", "size": len(texts), "negative_share": 0.2}]


class FakeUpload:
    def __init__(self, filename: str, path: Path) -> None:
        self.filename = filename
        self.file = path.open("rb")

    def close(self) -> None:
        self.file.close()


def make_csv(path: Path, rows: int = 100_000) -> None:
    phrases = [
        "Battery life is excellent and delivery was quick",
        "Support replied slowly but fixed the problem",
        "The app crashes after every update, very frustrating",
        "Great value for money and easy to set up",
        "Average quality, works well enough for daily use",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["text", "platform", "author", "timestamp"])
        for i in range(rows):
            text = phrases[i % len(phrases)]
            if i % 500 == 0:
                text = "BUY NOW limited time discount click here DM me"  # duplicate evidence
            writer.writerow([
                f"{text} order {i}",
                ["web", "X", "Reddit", "Google Reviews"][i % 4],
                f"user-{i % 200}",
                f"2026-01-{(i % 28) + 1:02d}T{(i % 24):02d}:00:00",
            ])


def main() -> None:
    sentiment.analyze_sentiment = _sentiment
    aspects.analyze_sentiment = _sentiment
    emotion.analyze_emotions = _emotion
    spam._nli_scores = _nli
    bot._nli_account = lambda _summary: None
    topics._clusters = _clusters

    db.init_db()
    with tempfile.TemporaryDirectory() as folder:
        csv_path = Path(folder) / "scale.csv"
        print(f"Generating {100_000:,} rows…")
        make_csv(csv_path)
        upload = FakeUpload("scale.csv", csv_path)

        from app.ingestion import build_preview

        preview = build_preview(files=[upload])
        upload.close()
        dataset_id = preview["dataset_id"]
        assert preview["count"] == 100_000, preview["counts"]
        assert "records" not in preview, "Large preview must not inline 100k records"
        assert len(preview["preview"]) == 10
        print("Staged:", dataset_id, preview["counts"])

        result = pipeline.run_analysis(
            "100k scale smoke",
            dataset_id=dataset_id,
            options={"period": "daily", "redact_pii": True},
        )
        run_id = result["id"]
        assert result["summary"]["total_records"] == 100_000
        assert len(result["bots"]["accounts"]) <= config.MAX_ACCOUNT_SUMMARIES
        assert result["storage"] == "streaming-jsonl"
        print("Analysed:", run_id, result["summary"]["sentiment_counts"])

        lines = sum(1 for _ in store.run_records_path(run_id).open(encoding="utf-8"))
        assert lines == 100_000, lines
        print("Enriched JSONL lines:", lines)

        suspicion = store.query_run_records(run_id, sort="suspicion", limit=5)
        scores = [r["suspicion_score"] for r in suspicion["records"]]
        assert suspicion["total"] == 100_000
        assert scores == sorted(scores, reverse=True), scores
        print("Top suspicion:", scores)

        lowest = store.query_run_records(run_id, sort="score", limit=5)
        sentiment_scores = [r["sentiment_score"] for r in lowest["records"]]
        assert sentiment_scores == sorted(sentiment_scores), sentiment_scores
        print("Lowest sentiment:", sentiment_scores)

        filtered = store.query_run_records(
            run_id, filters={"sentiment": "negative"}, sort="index", limit=3
        )
        assert filtered["total"] > 0
        assert all(r["sentiment"] == "negative" for r in filtered["records"])
        print("Filtered negative total:", filtered["total"])

        csv_bytes = reports.export_csv(result, sort="index")
        csv_lines = csv_bytes.count(b"\n")
        assert csv_lines == 100_001, csv_lines
        print("CSV export bytes/lines:", len(csv_bytes), csv_lines)

        pdf_bytes = reports.export_pdf(result)
        assert pdf_bytes.startswith(b"%PDF")
        print("PDF export bytes:", len(pdf_bytes))

        db.delete_run(run_id)
        store.delete_run_records(run_id)
        store.delete_dataset(dataset_id)
        print("Cleanup complete. SCALE SMOKE PASSED")


if __name__ == "__main__":
    main()
