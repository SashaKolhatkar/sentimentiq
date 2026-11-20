"""Request/response schemas shared by the API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from .config import INLINE_RECORD_LIMIT, MAX_TEXT_LENGTH, MAX_RECORDS


class RecordIn(BaseModel):
    id: str | None = None
    text: str
    platform: str = "unknown"
    author: str | None = None
    timestamp: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_type: str = "manual"
    is_demo: bool = False

    @field_validator("text")
    @classmethod
    def clean_text(cls, value: str) -> str:
        value = " ".join(str(value or "").split())
        if not value:
            raise ValueError("Text cannot be empty")
        return value[:MAX_TEXT_LENGTH]


class AnalyzeRequest(BaseModel):
    name: str = "Untitled analysis"
    records: list[RecordIn] = Field(default_factory=list)
    dataset_id: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)

    @field_validator("records")
    @classmethod
    def check_size(cls, value: list[RecordIn]) -> list[RecordIn]:
        if len(value) > INLINE_RECORD_LIMIT:
            raise ValueError(
                f"Inline requests support {INLINE_RECORD_LIMIT} records; "
                "use the staged dataset returned by /api/ingest/preview for larger files."
            )
        if len(value) > MAX_RECORDS:
            raise ValueError(f"Maximum {MAX_RECORDS} records per analysis")
        return value

    @model_validator(mode="after")
    def check_source(self) -> "AnalyzeRequest":
        if not self.dataset_id and not self.records:
            raise ValueError("Provide records or a dataset_id")
        return self


class LoginRequest(BaseModel):
    username: str
    password: str


class UrlRequest(BaseModel):
    url: str


class TextRequest(BaseModel):
    text: str
    platform: str = "unknown"
    split_lines: bool = True
