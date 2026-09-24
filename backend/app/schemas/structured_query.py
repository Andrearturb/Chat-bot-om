from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


QUERY_SHAPES = {"count", "list", "group", "ranking", "comparison"}
COMPARISON_DIMENSIONS = {
    "period",
    "praca",
    "store_name",
    "location_term",
    "analyst_responsible",
    "supplier",
    "requester",
    "category",
    "subcategory",
    "status",
}
BREAKDOWN_DIMENSIONS = {
    "praca",
    "store_name",
    "analyst_responsible",
    "supplier",
    "requester",
    "category",
    "subcategory",
    "status",
}
BREAKDOWN_ORDERS = {"absolute_change", "increase", "decrease"}


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


class ComparisonItem(BaseModel):
    label: str | None = None
    value: str | None = None
    year: int | None = Field(default=None, ge=1, le=9999)
    month: int | None = Field(default=None, ge=1, le=12)
    start_date: date | datetime | None = None
    end_date: date | datetime | None = None


class ComparisonSpec(BaseModel):
    dimension: Literal[
        "period",
        "praca",
        "store_name",
        "location_term",
        "analyst_responsible",
        "supplier",
        "requester",
        "category",
        "subcategory",
        "status",
    ]
    items: list[ComparisonItem] = Field(min_length=2, max_length=2)
    breakdown_by: Literal[
        "praca",
        "store_name",
        "analyst_responsible",
        "supplier",
        "requester",
        "category",
        "subcategory",
        "status",
    ] | None = None
    breakdown_order: Literal[
        "absolute_change",
        "increase",
        "decrease",
    ] | None = None
    breakdown_limit: int | None = Field(default=None, ge=1, le=100)


class StructuredQueryRequest(BaseModel):
    query_shape: str
    state: StructuredQueryState
    comparison: ComparisonSpec | None = None


class ComparisonBreakdownRow(BaseModel):
    label: str
    base_total: int
    target_total: int
    difference: int
    percentage_change: float | None
    direction: Literal["increase", "decrease", "stable"]


class ComparisonResult(BaseModel):
    dimension: str
    base_label: str
    target_label: str
    difference: int
    percentage_change: float | None
    direction: Literal["increase", "decrease", "stable"]
    breakdown_by: str | None = None
    breakdown_order: str | None = None


class StructuredQueryResponse(BaseModel):
    success: bool
    query_shape: str
    row_count: int
    truncated: bool
    columns: list[str]
    rows: list[dict[str, Any]]
    comparison: ComparisonResult | None = None
    breakdown: list[ComparisonBreakdownRow] | None = None
