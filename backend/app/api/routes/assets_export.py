"""Exportação de ativos (.xlsx): prévia das contagens e download. Exige assets.view."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db, require_permission
from app.models.auth import AppUser
from app.services.assets_export import (
    XLSX_MEDIA_TYPE, build_workbook, count_assets, export_filename, parse_types, select_stores,
)
from app.services.auth import record_audit

router = APIRouter(prefix="/assets/export", tags=["Assets"],
                   dependencies=[Depends(require_permission("assets.view"))])


def _resolve(db: Session, praca: list[str] | None, store_id: list[int] | None, asset_type: list[str] | None):
    if (praca and (len(praca) > 100 or any(len(value) > 150 for value in praca))) or (store_id and len(store_id) > 1000):
        raise HTTPException(status_code=422, detail="Filtro grande demais.")
    types = parse_types(asset_type)
    return select_stores(db, pracas=praca, store_ids=store_id), types


@router.get("/preview")
def export_preview(praca: list[str] | None = Query(default=None), store_id: list[int] | None = Query(default=None),
                   asset_type: list[str] | None = Query(default=None), db: Session = Depends(get_db)) -> dict:
    stores, types = _resolve(db, praca, store_id, asset_type)
    return {"stores": len(stores), **count_assets(db, stores, types)}


@router.get("")
def export_assets(praca: list[str] | None = Query(default=None), store_id: list[int] | None = Query(default=None),
                  asset_type: list[str] | None = Query(default=None),
                  user: AppUser = Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
    stores, types = _resolve(db, praca, store_id, asset_type)
    if not stores:
        raise HTTPException(status_code=400, detail="Nenhuma loja encontrada com esses filtros.")
    counts = count_assets(db, stores, types)
    content = build_workbook(db, stores, types)
    record_audit(db, user_id=user.id, action="ASSET_EXPORT", entity_type="asset_export",
                 new_values={"stores": len(stores), "assets": sum(counts.values()), "types": types,
                             "pracas": praca or [], "store_ids": store_id or []})
    db.commit()
    return Response(content=content, media_type=XLSX_MEDIA_TYPE, headers={
        "Content-Disposition": f'attachment; filename="{export_filename()}"', "Cache-Control": "no-store"})
