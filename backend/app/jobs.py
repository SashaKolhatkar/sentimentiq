"""Background analysis jobs with real progress reporting."""

from __future__ import annotations

import asyncio
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from . import db
from .analysis.pipeline import run_analysis
from .utils import new_id

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="sentimentiq-analysis")


def _worker(job_id: str, payload: dict[str, Any]) -> None:
    def progress(value: int, message: str) -> None:
        db.update_job(job_id, "running", value, message)

    try:
        db.update_job(job_id, "running", 2, "Starting analysis")
        result = run_analysis(
            name=payload.get("name", "Untitled analysis"),
            dataset_id=payload["dataset_id"],
            options=payload.get("options", {}),
            source_type=payload.get("source_type", "manual"),
            is_demo=bool(payload.get("is_demo", False)),
            progress=progress,
        )
        db.save_run(
            result["id"],
            result["name"],
            result["source_type"],
            result["is_demo"],
            result,
            record_count=result["summary"]["total_records"],
        )
        db.update_job(job_id, "complete", 100, "Analysis complete", result=result)
    except Exception as exc:
        db.update_job(
            job_id,
            "failed",
            0,
            "Analysis failed",
            error=f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=3)}",
        )


async def start_job(payload: dict[str, Any]) -> str:
    job_id = new_id("job_")
    db.create_job(job_id)
    loop = asyncio.get_running_loop()
    loop.run_in_executor(_executor, _worker, job_id, payload)
    return job_id
