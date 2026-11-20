"""SentimentIQ FastAPI application."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from fastapi import Body, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import config, db, models, reports, store
from .auth import (
    ROLES,
    authenticate,
    bootstrap_users,
    change_password,
    current_user,
    register_first_admin,
    register_user,
    require_admin,
    require_writer,
)
from .demo_data import demo_records
from .ingestion import build_preview
from .jobs import start_job
from .schemas import (
    AnalyzeRequest,
    LoginRequest,
    PasswordChangeRequest,
    PasswordResetRequest,
    RegisterRequest,
    TextRequest,
    UrlRequest,
    UserCreateRequest,
    UserUpdateRequest,
)
from .utils import new_id, to_jsonable

app = FastAPI(
    title="SentimentIQ API",
    version="1.0.0",
    description="Real NLP-powered social media and customer review intelligence.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    db.init_db()
    bootstrap_users()


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal error: {type(exc).__name__}: {str(exc)[:300]}"},
    )


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "SentimentIQ",
        "version": "1.0.0",
        "auth_enabled": config.AUTH_ENABLED,
        "python": "3.10+",
    }


@app.get("/api/config")
def public_config() -> dict[str, Any]:
    return {
        "auth_enabled": config.AUTH_ENABLED,
        "registration_open": config.AUTH_ENABLED and db.count_users() == 0,
        "themes": config.THEMES,
        "source_types": config.SOURCE_TYPES,
        "allowed_domains": config.ALLOWED_URL_DOMAINS,
        "max_file_size_mb": config.MAX_FILE_SIZE_MB,
        "max_records": config.MAX_RECORDS,
        "inline_record_limit": config.INLINE_RECORD_LIMIT,
        "analyze_limit": config.ANALYZE_LIMIT,
        "models": config.MODEL_IDS,
        "dataset_foundation": [
            {"name": "TweetEval – Sentiment", "role": "Sentiment model family"},
            {"name": "GoEmotions – Emotion", "role": "Emotion model family"},
            {"name": "Yelp Open Dataset", "role": "Customer review domain reference"},
            {"name": "YelpChi", "role": "Fake-review signal reference"},
            {"name": "TwiBot-22", "role": "Bot-detection signal reference"},
        ],
    }


@app.post("/api/auth/login")
def login(payload: LoginRequest, request: Request) -> dict[str, Any]:
    if not config.AUTH_ENABLED:
        return {
            "token": None,
            "user": {"id": "local", "username": "demo", "email": "", "role": "admin"},
            "auth_disabled": True,
        }
    client_key = request.client.host if request.client else "unknown"
    token, user = authenticate(payload.username, payload.password, client_key)
    if not token or not user:
        raise HTTPException(status_code=401, detail="Invalid credentials or too many attempts")
    return {"token": token, "user": user, "auth_disabled": False}


@app.post("/api/auth/register")
def register(payload: RegisterRequest) -> dict[str, Any]:
    if not config.AUTH_ENABLED:
        raise HTTPException(status_code=400, detail="Registration is disabled in local demo mode")
    try:
        token, user = register_first_admin(payload.username, payload.email, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"token": token, "user": user, "auth_disabled": False}


@app.get("/api/auth/me")
def me(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    return user


@app.post("/api/auth/password")
def update_own_password(
    payload: PasswordChangeRequest, user: dict[str, Any] = Depends(current_user)
) -> dict[str, bool]:
    if not config.AUTH_ENABLED:
        raise HTTPException(status_code=400, detail="Password changes require authentication to be enabled")
    try:
        change_password(user["id"], payload.new_password, payload.current_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"changed": True}


@app.get("/api/users")
def list_users(admin: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    return {"users": db.list_users(), "roles": list(ROLES)}


@app.post("/api/users")
def add_user(
    payload: UserCreateRequest, admin: dict[str, Any] = Depends(require_admin)
) -> dict[str, Any]:
    if payload.role not in ROLES:
        raise HTTPException(status_code=400, detail=f"Role must be one of: {', '.join(ROLES)}")
    try:
        return {"user": register_user(payload.username, payload.email, payload.password, payload.role)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch("/api/users/{user_id}")
def edit_user(
    user_id: str,
    payload: UserUpdateRequest,
    admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    target = db.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if payload.role is not None and payload.role not in ROLES:
        raise HTTPException(status_code=400, detail=f"Role must be one of: {', '.join(ROLES)}")
    if target["role"] == "admin" and db.count_admins() <= 1:
        if payload.role is not None and payload.role != "admin":
            raise HTTPException(status_code=400, detail="At least one admin account must remain")
        if payload.disabled is True:
            raise HTTPException(status_code=400, detail="At least one admin account must remain")
    changes = payload.model_dump(exclude_none=True)
    updated = db.update_user(user_id, **changes)
    return {"user": updated}


@app.delete("/api/users/{user_id}")
def remove_user(
    user_id: str, admin: dict[str, Any] = Depends(require_admin)
) -> dict[str, bool]:
    target = db.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    if target["role"] == "admin" and db.count_admins() <= 1:
        raise HTTPException(status_code=400, detail="At least one admin account must remain")
    return {"deleted": db.delete_user(user_id)}


@app.post("/api/users/{user_id}/password")
def reset_user_password(
    user_id: str,
    payload: PasswordResetRequest,
    admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, bool]:
    if not db.get_user_by_id(user_id):
        raise HTTPException(status_code=404, detail="User not found")
    change_password(user_id, payload.new_password)
    return {"changed": True}


@app.post("/api/ingest/preview")
async def ingest_preview(
    text: str = Form(""),
    split_lines: bool = Form(True),
    platform: str = Form("manual"),
    url: str = Form(""),
    files: list[UploadFile] = File(default=[]),
    user: dict[str, str] = Depends(current_user),
) -> dict[str, Any]:
    try:
        result = build_preview(
            text=text, split_lines=split_lines, files=files, url=url, platform=platform
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Ingestion failed: {exc}") from exc
    return to_jsonable(result)


@app.post("/api/ingest/text")
def ingest_text(payload: TextRequest, user: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
    from .ingestion import parse_pasted_text

    records = parse_pasted_text(payload.text, payload.split_lines, payload.platform)
    return to_jsonable({"records": records, "count": len(records)})


@app.post("/api/ingest/url")
def ingest_url(payload: UrlRequest, user: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
    from .ingestion import fetch_public_page

    try:
        records, warnings = fetch_public_page(payload.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return to_jsonable({"records": records, "warnings": warnings, "count": len(records)})


@app.get("/api/demo/dataset")
def get_demo_dataset(user: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
    records = demo_records()
    return to_jsonable(
        {
            "records": records,
            "count": len(records),
            "notice": "Hand-written demonstration data. Results are labelled DEMO in the UI and reports.",
        }
    )


@app.post("/api/analyze")
async def analyze(payload: AnalyzeRequest, user: dict[str, Any] = Depends(require_writer)) -> dict[str, str]:
    dataset_id = payload.dataset_id
    source_type = "manual"
    is_demo = False

    if dataset_id:
        try:
            meta = store.dataset_meta(dataset_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not meta:
            raise HTTPException(status_code=404, detail="Staged dataset not found or expired")
        source_type = meta["source_type"]
        is_demo = meta["is_demo"]
    else:
        dataset_id, _ = store.create_dataset(
            (r.model_dump() for r in payload.records),
            payload.records[0].source_type if payload.records else "manual",
            is_demo=is_demo,
        )
        source_type = payload.records[0].source_type if payload.records else "manual"
        is_demo = all(r.is_demo for r in payload.records)

    job_id = await start_job(
        {
            "name": payload.name,
            "dataset_id": dataset_id,
            "options": payload.options,
            "source_type": source_type,
            "is_demo": is_demo,
        }
    )
    return {"job_id": job_id, "status": "queued", "dataset_id": dataset_id}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str, user: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/api/runs")
def get_runs(limit: int = 50, user: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
    return {"runs": db.list_runs(limit)}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str, user: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
    run = db.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Analysis run not found")
    return run


@app.get("/api/runs/{run_id}/records")
def get_run_records(
    run_id: str,
    offset: int = 0,
    limit: int = 10,
    q: str = "",
    sentiment: str = "all",
    emotion: str = "all",
    platform: str = "all",
    spam: str = "all",
    bot: str = "all",
    sort: str = "index",
    user: dict[str, str] = Depends(current_user),
) -> dict[str, Any]:
    try:
        return store.query_run_records(
            run_id,
            offset=offset,
            limit=limit,
            filters={"q": q, "sentiment": sentiment, "emotion": emotion,
                     "platform": platform, "spam": spam, "bot": bot},
            sort=sort,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/api/runs/{run_id}")
def remove_run(run_id: str, user: dict[str, Any] = Depends(require_writer)) -> dict[str, bool]:
    deleted = db.delete_run(run_id)
    store.delete_run_records(run_id)
    return {"deleted": deleted}


@app.get("/api/models/status")
def get_model_status(user: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
    return {"models": models.model_status()}


@app.post("/api/models/warm")
async def warm_models(
    payload: dict[str, Any] = Body(default={}),
    user: dict[str, str] = Depends(current_user),
) -> dict[str, Any]:
    keys = payload.get("keys")
    if keys is not None and (not isinstance(keys, list) or any(k not in config.MODEL_IDS for k in keys)):
        raise HTTPException(status_code=400, detail="Unknown model key")
    return models.warm_models(keys)


@app.get("/api/reports/{run_id}/{fmt}")
def download_report(
    run_id: str,
    fmt: str,
    q: str = "",
    sentiment: str = "all",
    emotion: str = "all",
    platform: str = "all",
    spam: str = "all",
    bot: str = "all",
    sort: str = "index",
    user: dict[str, str] = Depends(current_user),
) -> Response:
    run = db.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Analysis run not found")
    fmt = fmt.lower()
    exporters = {"csv": reports.export_csv, "excel": reports.export_excel, "pdf": reports.export_pdf}
    exporter = exporters.get(fmt)
    if not exporter:
        raise HTTPException(status_code=400, detail="Supported formats: csv, excel, pdf")
    try:
        if fmt == "csv":
            payload = exporter(
                run,
                filters={"q": q, "sentiment": sentiment, "emotion": emotion,
                         "platform": platform, "spam": spam, "bot": bot},
                sort=sort,
            )
        else:
            payload = exporter(run)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Report generation failed: {exc}") from exc
    ext = {"csv": "csv", "excel": "xlsx", "pdf": "pdf"}[fmt]
    mime = {
        "csv": "text/csv; charset=utf-8",
        "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "pdf": "application/pdf",
    }[fmt]
    filename = f"sentimentiQ-{run_id[:8]}.{ext}".lower()
    db.save_report(new_id("rep_"), run_id, fmt, filename)
    return Response(
        content=payload,
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/reports/history")
def report_history(user: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
    return {"reports": db.list_reports()}


# ---------------------------------------------------------------------------
# Optional static SPA hosting.  Build the frontend and it is served from here.
# ---------------------------------------------------------------------------
DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if (DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        candidate = DIST / full_path
        if candidate.is_file() and DIST in candidate.resolve().parents:
            return FileResponse(candidate)
        return FileResponse(DIST / "index.html")

else:

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_placeholder(full_path: str):
        return {
            "message": "SentimentIQ API is running. Build the frontend with `npm run build` "
            "inside the frontend folder to serve the dashboard here.",
            "path": full_path,
        }
