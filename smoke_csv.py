"""CSV ingestion + analysis smoke test."""

import time

import httpx

with httpx.Client(base_url="http://127.0.0.1:8000", timeout=240, trust_env=False) as c:
    with open("sample_data.csv", "rb") as f:
        preview = c.post(
            "/api/ingest/preview",
            data={"text": "", "split_lines": "true", "platform": "manual", "url": ""},
            files={"files": ("sample_data.csv", f, "text/csv")},
        ).json()
    print("preview:", preview["counts"])

    job = c.post(
        "/api/analyze",
        json={
            "name": "CSV smoke",
            "dataset_id": preview["dataset_id"],
            "options": {"period": "daily", "start": "2026-11-02", "end": "2026-11-03"},
        },
    ).json()["job_id"]
    while True:
        status = c.get(f"/api/jobs/{job}").json()
        if status["status"] in {"complete", "failed"}:
            break
        time.sleep(1)
    print("status:", status["status"])
    if status["status"] == "failed":
        print(status["error"])
    else:
        r = status["result"]
        print("records:", r["summary"]["total_records"])
        print("trend range:", r["trends"]["start"], r["trends"]["end"])
        print("spam:", r["summary"]["spam"]["labels"])
        print("bots:", r["summary"]["bots"]["labels"])
