"""Contrato restrito da consulta de ativos usada pelo assistente."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

AssetType = Literal["climatization", "fire_safety", "water"]
GroupBy = Literal["asset_type", "store_name", "praca", "status", "equipment_type", "brand", "location"]


class AssetQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, max_length=36)
    access_token: str = Field(min_length=1, max_length=1024)
    query_shape: Literal["count", "list", "group", "ranking"]
    asset_types: list[AssetType] = Field(default_factory=list, max_length=3)
    store_name: str | None = Field(default=None, max_length=150)
    praca: str | None = Field(default=None, max_length=150)
    status: str | None = Field(default=None, max_length=60)
    equipment_type: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=150)
    brand: str | None = Field(default=None, max_length=150)
    asset_code: str | None = Field(default=None, max_length=100)
    bpcs_number: str | None = Field(default=None, max_length=100)
    sap_number: str | None = Field(default=None, max_length=100)
    store_code: str | None = Field(default=None, max_length=100)
    capacity_btu_min: int | None = Field(default=None, ge=0, le=1000000)
    capacity_btu_max: int | None = Field(default=None, ge=0, le=1000000)
    due_before: date | None = None
    group_by: GroupBy | None = None
    limit: int | None = Field(default=None, ge=1, le=100)

    @model_validator(mode="after")
    def validate_shape(self):
        if self.query_shape in {"group", "ranking"} and self.group_by is None:
            raise ValueError("group_by é obrigatório para agrupamentos e rankings.")
        if self.query_shape in {"count", "list"} and self.group_by is not None:
            raise ValueError("group_by só é permitido para agrupamentos e rankings.")
        if self.capacity_btu_min is not None and self.capacity_btu_max is not None:
            if self.capacity_btu_min > self.capacity_btu_max:
                raise ValueError("capacity_btu_min não pode superar capacity_btu_max.")
        return self
