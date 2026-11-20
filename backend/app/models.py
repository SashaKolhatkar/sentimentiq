"""Lazy Hugging Face model manager.

All models are downloaded on demand (or from the Settings page) and cached
inside backend/data/models.  Any load failure is surfaced to the caller so the
analysis pipeline can switch to its transparent offline fallback.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from . import config

_state: dict[str, Any] = {}
_lock = threading.RLock()
_load_errors: dict[str, str] = {}


def _hub_dir(model_id: str) -> Path:
    return Path(config.HF_HOME) / "hub" / ("models--" + model_id.replace("/", "--"))


def is_cached(model_id: str) -> bool:
    path = _hub_dir(model_id)
    if not path.exists():
        return False
    return any(path.rglob("*.safetensors")) or any(path.rglob("*.bin")) or any(
        path.rglob("model.onnx")
    )


def _load(key: str, factory):
    with _lock:
        if key in _state:
            return _state[key]
        try:
            _state[key] = factory()
            _load_errors.pop(key, None)
            return _state[key]
        except Exception as exc:  # pragma: no cover - network/hardware dependent
            _load_errors[key] = f"{type(exc).__name__}: {exc}"
            raise


def sentiment_pipeline():
    from transformers import pipeline

    return _load(
        "sentiment",
        lambda: pipeline(
            "sentiment-analysis",
            model=config.SENTIMENT_MODEL,
            tokenizer=config.SENTIMENT_MODEL,
            device=config.DEVICE,
            truncation=True,
            max_length=512,
        ),
    )


def emotion_pipeline():
    from transformers import pipeline

    return _load(
        "emotion",
        lambda: pipeline(
            "text-classification",
            model=config.EMOTION_MODEL,
            tokenizer=config.EMOTION_MODEL,
            device=config.DEVICE,
            top_k=None,
            truncation=True,
            max_length=512,
        ),
    )


def nli_pipeline():
    from transformers import pipeline

    return _load(
        "nli",
        lambda: pipeline(
            "zero-shot-classification",
            model=config.NLI_MODEL,
            tokenizer=config.NLI_MODEL,
            device=config.DEVICE,
            truncation=True,
            max_length=512,
        ),
    )


def embedding_components():
    from transformers import AutoModel, AutoTokenizer

    def factory():
        tokenizer = AutoTokenizer.from_pretrained(config.EMBEDDING_MODEL)
        model = AutoModel.from_pretrained(config.EMBEDDING_MODEL)
        if config.DEVICE >= 0:
            model.to(config.DEVICE)
        model.eval()
        return {"tokenizer": tokenizer, "model": model}

    return _load("embedding", factory)


def embedded_texts(texts: list[str]) -> Any | None:
    """Mean-pooled, L2-normalised embeddings.  Returns None on failure."""
    if not texts:
        return None
    try:
        import numpy as np
        import torch

        components = embedding_components()
        tokenizer, model = components["tokenizer"], components["model"]
        device = config.DEVICE if config.DEVICE >= 0 else "cpu"
        encoded = tokenizer(
            texts, padding=True, truncation=True, max_length=256, return_tensors="pt"
        )
        encoded = {k: v.to(device) for k, v in encoded.items()}
        with torch.no_grad():
            output = model(**encoded)
        mask = encoded["attention_mask"].unsqueeze(-1).float()
        pooled = (output.last_hidden_state.float() * mask).sum(dim=1) / mask.sum(
            dim=1
        ).clamp(min=1e-9)
        pooled = torch.nn.functional.normalize(pooled, p=2, dim=1)
        return pooled.cpu().numpy().astype(np.float32)
    except Exception:
        return None


def model_status() -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, model_id in config.MODEL_IDS.items():
        result[key] = {
            "id": model_id,
            "cached": is_cached(model_id),
            "loaded": key in _state,
            "error": _load_errors.get(key),
        }
    return result


def warm_models(keys: list[str] | None = None) -> dict[str, Any]:
    targets = keys or list(config.MODEL_IDS)
    loaders = {
        "sentiment": sentiment_pipeline,
        "emotion": emotion_pipeline,
        "nli": nli_pipeline,
        "embedding": embedding_components,
    }
    report: dict[str, Any] = {}
    for key in targets:
        loader = loaders.get(key)
        if not loader:
            continue
        try:
            loader()
            report[key] = {"ok": True, "id": config.MODEL_IDS[key]}
        except Exception as exc:
            report[key] = {"ok": False, "error": str(exc)[:500]}
    return {"models": report, "status": model_status()}
