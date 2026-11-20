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


def _clean_username(value: str) -> str:
    value = " ".join(str(value or "").split())
    if len(value) < 3:
        raise ValueError("Username must be at least 3 characters")
    if len(value) > 64:
        raise ValueError("Username must be at most 64 characters")
    return value


def _clean_password(value: str) -> str:
    if len(str(value or "")) < 8:
        raise ValueError("Password must be at least 8 characters")
    if len(str(value)) > 256:
        raise ValueError("Password must be at most 256 characters")
    return value


def _clean_email(value: str | None) -> str | None:
    value = (value or "").strip()
    if not value:
        return None
    if "@" not in value or "." not in value.split("@")[-1]:
        raise ValueError("Enter a valid email address")
    return value[:254]


class RegisterRequest(BaseModel):
    username: str
    email: str | None = None
    password: str

    _username = field_validator("username")(_clean_username)
    _email = field_validator("email")(_clean_email)
    _password = field_validator("password")(_clean_password)


class UserCreateRequest(RegisterRequest):
    role: str = "analyst"


class UserUpdateRequest(BaseModel):
    email: str | None = None
    role: str | None = None
    disabled: bool | None = None

    _email = field_validator("email")(_clean_email)


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str

    _new_password = field_validator("new_password")(_clean_password)


class PasswordResetRequest(BaseModel):
    new_password: str

    _new_password = field_validator("new_password")(_clean_password)


class UrlRequest(BaseModel):
    url: str


class TextRequest(BaseModel):
    text: str
    platform: str = "unknown"
    split_lines: bool = True
