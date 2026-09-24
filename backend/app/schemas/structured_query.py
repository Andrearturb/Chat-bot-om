from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


QUERY_SHAPES = {"count", "list", "group", "ranking"}


class StructuredQueryState(BaseModel):
    model_config = ConfigDict(extra="allow")

    event: str | None = None
    date_field: Literal["created_on", "completion_date", "visit_date"] | None = None
    year: int | None = Field(default=None, ge=1, le=9999)
    month: int | None = Field(default=None, ge=1, le=12)
    start_date: date | datetime | None = None
    end_date: date | datetime | None = None

    praca: str | None = None
    store_name: str | None = None
    location_term: str | None = None

    status: str | None = None
    statuses: list[str] | None = None
    analyst_responsible: str | None = None
    supplier: str | None = None
    requester: str | None = None
    category: str | None = None
    subcategory: str | None = None

    missing_field: str | None = None
    group_by: str | None = None
    limit: int | None = Field(default=None, ge=1, le=200)

    @field_validator("statuses")
    @classmethod
    def reject_empty_statuses(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and not value:
            return None
        return value


class StructuredQueryRequest(BaseModel):
    query_shape: str
    state: StructuredQueryState


class StructuredQueryResponse(BaseModel):
    success: bool
    query_shape: str
    row_count: int
    truncated: bool
    columns: list[str]
    rows: list[dict[str, Any]]
