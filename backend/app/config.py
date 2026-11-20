"""Central configuration for SentimentIQ.

Environment variables are read once at import time.  Keep this module free of
heavyweight imports: it is imported before the model manager so that the HF
cache can be redirected early.
"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
MODEL_DIR = DATA_DIR / "models"
REPORT_DIR = DATA_DIR / "reports"
UPLOAD_DIR = DATA_DIR / "uploads"
DATASET_DIR = DATA_DIR / "datasets"
RUN_DIR = DATA_DIR / "runs"
DB_PATH = DATA_DIR / "sentimentiq.db"

for directory in (DATA_DIR, MODEL_DIR, REPORT_DIR, UPLOAD_DIR, DATASET_DIR, RUN_DIR):
    directory.mkdir(parents=True, exist_ok=True)

# Redirect HF caches before transformers is imported anywhere else.
HF_HOME = os.getenv("HF_HOME", str(MODEL_DIR))
os.environ.setdefault("HF_HOME", HF_HOME)
os.environ.setdefault("TRANSFORMERS_CACHE", str(Path(HF_HOME) / "hub"))
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# Real open models used by the analysis modules.
SENTIMENT_MODEL = os.getenv(
    "SENTIMENTIQ_SENTIMENT_MODEL", "cardiffnlp/twitter-roberta-base-sentiment-latest"
)
EMOTION_MODEL = os.getenv(
    "SENTIMENTIQ_EMOTION_MODEL", "SamLowe/roberta-base-go_emotions"
)
NLI_MODEL = os.getenv(
    "SENTIMENTIQ_NLI_MODEL", "typeform/distilbert-base-uncased-mnli"
)
EMBEDDING_MODEL = os.getenv(
    "SENTIMENTIQ_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
)

MODEL_IDS = {
    "sentiment": SENTIMENT_MODEL,
    "emotion": EMOTION_MODEL,
    "nli": NLI_MODEL,
    "embedding": EMBEDDING_MODEL,
}

# Authentication is enabled only when a password is supplied.  This keeps the
# local demo frictionless while production deployments stay protected.
AUTH_ENABLED = os.getenv("SENTIMENTIQ_AUTH_ENABLED", "").lower() in {
    "1", "true", "yes", "on"
}
ADMIN_USERNAME = os.getenv("SENTIMENTIQ_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("SENTIMENTIQ_ADMIN_PASSWORD", "")
SECRET_KEY = os.getenv(
    "SENTIMENTIQ_SECRET_KEY", "dev-only-change-this-secret-in-production"
)
TOKEN_TTL_SECONDS = int(os.getenv("SENTIMENTIQ_TOKEN_TTL", str(12 * 60 * 60)))

# Upload / ingestion limits.
MAX_FILE_SIZE_MB = int(os.getenv("SENTIMENTIQ_MAX_FILE_MB", "200"))
MAX_RECORDS = int(os.getenv("SENTIMENTIQ_MAX_RECORDS", "250000"))
# Inline JSON payloads are kept small; larger uploads are staged server-side.
INLINE_RECORD_LIMIT = int(os.getenv("SENTIMENTIQ_INLINE_RECORDS", "500"))
# Analysis is bounded so a single job cannot exhaust RAM. Anything above this
# is truncated with an explicit warning in the report.
ANALYZE_LIMIT = int(os.getenv("SENTIMENTIQ_ANALYZE_LIMIT", "100000"))
CHUNK_SIZE = int(os.getenv("SENTIMENTIQ_CHUNK_SIZE", "2000"))
MAX_TEXT_LENGTH = int(os.getenv("SENTIMENTIQ_MAX_TEXT_LENGTH", "4000"))
ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".txt"}
ALLOWED_URL_DOMAINS = [
    d.strip().lower()
    for d in os.getenv(
        "SENTIMENTIQ_ALLOWED_DOMAINS",
        "reddit.com,www.reddit.com,old.reddit.com,yelp.com,www.yelp.com,"
        "trustpilot.com,www.trustpilot.com,amazon.com,www.amazon.com,"
        "youtube.com,www.youtube.com,x.com,twitter.com,www.twitter.com,"
        "instagram.com,www.instagram.com,facebook.com,www.facebook.com",
    ).split(",")
    if d.strip()
]
URL_FETCH_TIMEOUT = float(os.getenv("SENTIMENTIQ_URL_TIMEOUT", "12"))
URL_MAX_BYTES = int(os.getenv("SENTIMENTIQ_URL_MAX_BYTES", str(2 * 1024 * 1024)))

# Analysis batching / model runtime.
BATCH_SIZE = int(os.getenv("SENTIMENTIQ_BATCH_SIZE", "32"))
INFERENCE_CHUNK = int(os.getenv("SENTIMENTIQ_INFERENCE_CHUNK", "1000"))
MAX_WORKERS = int(os.getenv("SENTIMENTIQ_MAX_WORKERS", "2"))
DEVICE = int(os.getenv("SENTIMENTIQ_DEVICE", "-1"))  # -1 CPU, 0 first GPU.
# Bounded work for quadratic-style similarity checks on large datasets.
LSH_BITS = 16
MAX_COMPARE_PER_ROW = 64
MAX_NLI_ACCOUNTS = 300
MAX_ACCOUNT_SUMMARIES = int(os.getenv("SENTIMENTIQ_MAX_ACCOUNT_SUMMARIES", "500"))
TOPIC_FIT_SAMPLE = int(os.getenv("SENTIMENTIQ_TOPIC_FIT_SAMPLE", "20000"))
SORT_CHUNK_SIZE = int(os.getenv("SENTIMENTIQ_SORT_CHUNK_SIZE", "50000"))

CORS_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "SENTIMENTIQ_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if o.strip()
]

THEMES = ["light", "dark", "pastel"]

SOURCE_TYPES = {
    "manual": "Manual text",
    "paste": "Pasted comments",
    "file": "Uploaded file",
    "url": "Public web page",
    "demo": "Built-in demo dataset",
}
