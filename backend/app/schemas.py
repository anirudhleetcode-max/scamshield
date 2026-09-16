from typing import Literal

from pydantic import BaseModel, Field, field_validator

from ml.templates import SCAM_CATEGORIES

Kind = Literal["phone", "upi", "url"]
ReportCategory = Literal[tuple(SCAM_CATEGORIES + ["other"])]  # type: ignore[valid-type]


class CheckIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    sender: str | None = Field(default=None, max_length=40)

    @field_validator("text")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Message is empty")
        return v

    @field_validator("sender")
    @classmethod
    def blank_to_none(cls, v: str | None) -> str | None:
        return v.strip() or None if v else None


class LookupIn(BaseModel):
    value: str = Field(min_length=3, max_length=500)
    kind: Literal["phone", "upi", "url", "upi_link"] | None = None


class ReportIn(BaseModel):
    kind: Kind
    value: str = Field(min_length=3, max_length=500)
    category: ReportCategory = "other"
    note: str | None = Field(default=None, max_length=280)
