"""Contratos restritos das consultas preventivas e de custos no chat."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


Shape = Literal["count", "list", "group", "ranking"]


class QueryBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, max_length=100)
    access_token: str = Field(min_length=1, max_length=1024)
    query_shape: Shape
    store_name: str | None = Field(default=None, max_length=150)
    praca: str | None = Field(default=None, max_length=150)
    year: int | None = Field(default=None, ge=2000, le=2100)
    month: int | None = Field(default=None, ge=1, le=12)
    start_date: date | None = None
    end_date: date | None = None
    limit: int | None = Field(default=None, ge=1, le=100)

    @model_validator(mode="after")
    def validate_period(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date não pode superar end_date.")
        return self


PreventiveGroup = Literal[
    "store_name", "praca", "status", "periodicity", "category", "subcategory", "supplier",
]


class PreventiveQueryRequest(QueryBase):
    status: str | None = Field(default=None, max_length=100)
    periodicity: str | None = Field(default=None, max_length=100)
    category: str | None = Field(default=None, max_length=150)
    subcategory: str | None = Field(default=None, max_length=150)
    supplier: str | None = Field(default=None, max_length=150)
    date_field: Literal["created_on", "completion_date", "visit_date", "due_date"] = "created_on"
    overdue: bool | None = None
    group_by: PreventiveGroup | None = None

    @model_validator(mode="after")
    def validate_shape(self):
        if (self.query_shape in {"group", "ranking"}) != (self.group_by is not None):
            raise ValueError("group_by é obrigatório somente para group e ranking.")
        return self


CostGroup = Literal["store_name", "praca", "supplier", "conta_razao", "year", "month"]


class CostQueryRequest(QueryBase):
    conta_razao: str | None = Field(default=None, max_length=30)
    supplier: str | None = Field(default=None, max_length=150)
    unattributed: bool | None = None
    unsupported_filter: str | None = Field(default=None, max_length=100)
    group_by: CostGroup | None = None

    @model_validator(mode="after")
    def validate_shape(self):
        if (self.query_shape in {"group", "ranking"}) != (self.group_by is not None):
            raise ValueError("group_by é obrigatório somente para group e ranking.")
        return self
