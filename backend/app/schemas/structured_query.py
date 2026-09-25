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
MULTI_FILTER_DIMENSIONS = {
    "praca",
    "store_name",
    "location_term",
    "analyst_responsible",
    "supplier",
    "requester",
    "category",
    "subcategory",
}
SELECTION_MODES = {"comparison_items", "top_drivers", "offsets", "breakdown"}


class MultiFilterSpec(BaseModel):
    """Filtros OR por dimensão, combinados com AND entre dimensões."""

    model_config = ConfigDict(extra="forbid")

    praca: list[str] | None = Field(default=None, max_length=100)
    store_name: list[str] | None = Field(default=None, max_length=100)
    location_term: list[str] | None = Field(default=None, max_length=100)
    analyst_responsible: list[str] | None = Field(default=None, max_length=100)
    supplier: list[str] | None = Field(default=None, max_length=100)
    requester: list[str] | None = Field(default=None, max_length=100)
    category: list[str] | None = Field(default=None, max_length=100)
    subcategory: list[str] | None = Field(default=None, max_length=100)

    @field_validator(
        "praca",
        "store_name",
        "location_term",
        "analyst_responsible",
        "supplier",
        "requester",
        "category",
        "subcategory",
    )
    @classmethod
    def normalize_values(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None

        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            text = str(item).strip()
            if not text:
                continue
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(text)

        return normalized or None


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

    # Filtros múltiplos: OR dentro da dimensão, AND entre dimensões.
    multi_filters: MultiFilterSpec | None = None

    missing_field: str | None = None
    group_by: str | None = None
    limit: int | None = Field(default=None, ge=1, le=200)

    # Opções estruturais específicas de listagens.
    # `limit` continua reservado para ranking/group; listagens usam list_limit.
    list_limit: int | None = Field(default=None, ge=1, le=200)
    sort_by: Literal["created_on", "completion_date", "visit_date", "ticket"] | None = None
    sort_order: Literal["asc", "desc"] | None = None

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

    # Detalhamento simples de uma unica dimensao.
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

    # Analise deterministica de drivers da variacao.
    # Continua dentro de comparison para ser persistida na mesma coluna da Data Table.
    analysis_mode: Literal["drivers"] | None = None
    driver_dimensions: list[
        Literal[
            "praca",
            "store_name",
            "analyst_responsible",
            "supplier",
            "requester",
            "category",
            "subcategory",
            "status",
        ]
    ] | None = Field(default=None, min_length=1, max_length=5)
    driver_limit: int | None = Field(default=None, ge=1, le=10)

    @field_validator("driver_dimensions")
    @classmethod
    def unique_driver_dimensions(
        cls,
        value: list[str] | None,
    ) -> list[str] | None:
        if value is None:
            return None
        return list(dict.fromkeys(value))


class SelectionContextSpec(BaseModel):
    """Referência persistente a grupos produzidos por uma comparação anterior."""

    source: Literal["previous_comparison"] = "previous_comparison"
    mode: Literal["comparison_items", "top_drivers", "offsets", "breakdown"]
    dimension: Literal[
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
    limit: int | None = Field(default=None, ge=1, le=100)
    source_state: StructuredQueryState
    source_comparison: ComparisonSpec


class StructuredQueryRequest(BaseModel):
    query_shape: str
    state: StructuredQueryState
    comparison: ComparisonSpec | None = None
    selection_context: SelectionContextSpec | None = None


class ComparisonBreakdownRow(BaseModel):
    label: str
    base_total: int
    target_total: int
    difference: int
    percentage_change: float | None
    direction: Literal["increase", "decrease", "stable"]


class ComparisonDriverRow(BaseModel):
    label: str
    base_total: int
    target_total: int
    difference: int
    percentage_change: float | None
    direction: Literal["increase", "decrease", "stable"]
    contribution_pct: float | None


class ComparisonDriverDimension(BaseModel):
    dimension: str
    gross_driver_change: int
    gross_offset_change: int
    top_drivers: list[ComparisonDriverRow]
    offsets: list[ComparisonDriverRow]


class ComparisonDriverAnalysis(BaseModel):
    mode: Literal["drivers"]
    net_difference: int
    direction: Literal["increase", "decrease", "stable"]
    dimensions: list[ComparisonDriverDimension]


class ComparisonResult(BaseModel):
    dimension: str
    base_label: str
    target_label: str
    difference: int
    percentage_change: float | None
    direction: Literal["increase", "decrease", "stable"]
    breakdown_by: str | None = None
    breakdown_order: str | None = None
    analysis_mode: str | None = None
    driver_dimensions: list[str] | None = None
    driver_limit: int | None = None


class ResolvedSelectionResult(BaseModel):
    source: Literal["previous_comparison"]
    mode: str
    dimension: str
    values: list[str]
    inherited_comparison_scope: bool


class StructuredQueryResponse(BaseModel):
    success: bool
    query_shape: str
    row_count: int
    truncated: bool
    columns: list[str]
    rows: list[dict[str, Any]]
    # Metadados de listagem: total que atende aos filtros versus linhas exibidas.
    total_count: int | None = None
    list_limit: int | None = None
    sort_by: str | None = None
    sort_order: str | None = None
    comparison: ComparisonResult | None = None
    breakdown: list[ComparisonBreakdownRow] | None = None
    driver_analysis: ComparisonDriverAnalysis | None = None
    resolved_selection: ResolvedSelectionResult | None = None
