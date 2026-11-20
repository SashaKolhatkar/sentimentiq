"""End-to-end API smoke test. Run while backend is on 127.0.0.1:8000."""

import time

import httpx

BASE = "http://127.0.0.1:8000"


def main() -> None:
    with httpx.Client(base_url=BASE, timeout=240, trust_env=False) as client:
        health = client.get("/api/health").json()
        print("health:", health["ok"], health["service"])

        records = client.get("/api/demo/dataset").json()["records"]
        print("demo records:", len(records))

        job = client.post(
            "/api/analyze",
            json={"name": "API smoke demo", "records": records, "options": {"period": "daily"}},
        ).json()["job_id"]
        print("job:", job)

        while True:
            status = client.get(f"/api/jobs/{job}").json()
            if status["status"] in {"complete", "failed"}:
                break
            time.sleep(1)
        print("status:", status["status"], status["progress"])
        if status["status"] == "failed":
            print(status["error"])
            return

        result = status["result"]
        print("run:", result["id"])
        print("summary:", result["summary"]["sentiment_counts"], result["summary"]["spam"]["labels"])
        print(
            "reports:",
            {
                fmt: len(client.get(f"/api/reports/{result['id']}/{fmt}").content)
                for fmt in ("csv", "excel", "pdf")
            },
        )
        models = client.get("/api/models/status").json()["models"]
        print("models:", {k: (v["cached"], v["loaded"]) for k, v in models.items()})


if __name__ == "__main__":
    main()
