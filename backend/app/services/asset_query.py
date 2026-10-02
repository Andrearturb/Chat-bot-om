"""Consulta de leitura dos três inventários, sem SQL gerado pelo modelo de IA."""

from __future__ import annotations

import unicodedata

from sqlalchemy import Date, Integer, String, and_, func, literal, or_, select, union_all
from sqlalchemy.orm import Session

from app.models.asset_store import AssetStore
from app.models.climate_asset import ClimateAsset
from app.models.fire_asset import FireAsset
from app.models.water_asset import WaterAsset
from app.schemas.asset_query import AssetQueryRequest


def _asset_rows(model, asset_type: str):
    return select(
        literal(asset_type).label("asset_type"),
        model.asset_code.label("asset_code"),
        AssetStore.store_name.label("store_name"),
        AssetStore.praca.label("praca"),
        AssetStore.bpcs_number.label("bpcs_number"),
        AssetStore.sap_number.label("sap_number"),
        model.equipment_type.label("equipment_type"),
        model.location.label("location"),
        model.status.label("status"),
        (model.brand if hasattr(model, "brand") else literal(None).cast(String)).label("brand"),
        (model.model if hasattr(model, "model") else literal(None).cast(String)).label("model"),
        (model.capacity_btu if hasattr(model, "capacity_btu") else literal(None).cast(Integer)).label("capacity_btu"),
        (model.expiration_date if hasattr(model, "expiration_date") else literal(None).cast(Date)).label("expiration_date"),
        (model.next_filter_change if hasattr(model, "next_filter_change") else literal(None).cast(Date)).label("next_filter_change"),
    ).join(AssetStore, AssetStore.id == model.store_id)


def _like_term(value: str) -> str:
    return value.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _location_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    return "".join(char for char in normalized if not unicodedata.combining(char)).strip()


def _filtered_rows(request: AssetQueryRequest):
    rows = union_all(
        _asset_rows(ClimateAsset, "climatization"),
        _asset_rows(FireAsset, "fire_safety"),
        _asset_rows(WaterAsset, "water"),
    ).subquery("assets")
    conditions = []
    if request.asset_types:
        conditions.append(rows.c.asset_type.in_(request.asset_types))
    for field in ("store_name", "praca", "equipment_type", "brand", "asset_code", "bpcs_number", "sap_number"):
        value = getattr(request, field)
        if value:
            # LIKE com escape: % e _ digitados pelo usuário são tratados como texto.
            conditions.append(getattr(rows.c, field).ilike(f"%{_like_term(value)}%", escape="\\"))
    if request.store_code:
        # A IA não sabe se um código de loja falado pelo usuário é o número BPCS ou
        # o SAP sem consultar o cadastro, então buscamos nos dois campos.
        term = f"%{_like_term(request.store_code)}%"
        conditions.append(or_(rows.c.bpcs_number.ilike(term, escape="\\"),
                              rows.c.sap_number.ilike(term, escape="\\")))
    if request.location:
        location = _location_key(request.location)
        if location in {"salao", "salao de venda", "salao de vendas"}:
            # O inventário usa "Salão" para o salão de vendas.
            conditions.append(or_(rows.c.location.ilike("%salão%"), rows.c.location.ilike("%salao%")))
        else:
            conditions.append(rows.c.location.ilike(f"%{_like_term(request.location)}%", escape="\\"))
    if request.status:
        conditions.append(func.lower(func.trim(rows.c.status)) == request.status.strip().lower())
    if request.capacity_btu_min is not None:
        conditions.append(rows.c.capacity_btu >= request.capacity_btu_min)
    if request.capacity_btu_max is not None:
        conditions.append(rows.c.capacity_btu <= request.capacity_btu_max)
    if request.due_before:
        conditions.append(or_(
            and_(rows.c.asset_type == "fire_safety", rows.c.expiration_date <= request.due_before),
            and_(rows.c.asset_type == "water", rows.c.next_filter_change <= request.due_before),
        ))
    return rows, conditions


def execute_asset_query(db: Session, request: AssetQueryRequest) -> dict:
    rows, conditions = _filtered_rows(request)
    where = and_(*conditions) if conditions else literal(True)

    if request.query_shape == "count":
        total = db.scalar(select(func.count()).select_from(rows).where(where)) or 0
        locations = []
        if request.location and total:
            locations = [dict(row) for row in db.execute(
                select(rows.c.location.label("location"), func.count().label("total"))
                .select_from(rows).where(where).group_by(rows.c.location)
                .order_by(func.count().desc(), rows.c.location).limit(10)
            ).mappings().all()]
        return {"query_shape": "count", "total_count": total, "rows": [{"total": total}],
                "matched_locations": locations, "truncated": False}

    if request.query_shape == "list":
        limit = min(request.limit or 20, 50)
        total = db.scalar(select(func.count()).select_from(rows).where(where)) or 0
        result = db.execute(
            select(rows).where(where).order_by(rows.c.store_name, rows.c.asset_type, rows.c.asset_code).limit(limit)
        ).mappings().all()
        return {
            "query_shape": "list", "total_count": total,
            "rows": [dict(row) for row in result], "truncated": total > len(result),
        }

    group_column = getattr(rows.c, request.group_by)
    total_groups = db.scalar(select(func.count()).select_from(
        select(group_column).where(where).group_by(group_column).subquery()
    )) or 0
    limit = min(request.limit or (10 if request.query_shape == "ranking" else 100), 100)
    statement = (
        select(group_column.label(request.group_by), func.count().label("total"))
        .select_from(rows).where(where).group_by(group_column)
        .order_by(func.count().desc(), group_column).limit(limit)
    )
    result = db.execute(statement).mappings().all()
    return {
        "query_shape": request.query_shape, "group_by": request.group_by,
        "total_count": total_groups, "rows": [dict(row) for row in result],
        "truncated": total_groups > len(result),
    }
