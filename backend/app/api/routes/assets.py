"""
Central de Ativos — permissões granulares + auditoria.

GET  → assets.view
POST → assets.create  (+ CSRF)
PUT  → assets.edit    (+ CSRF)
DELETE → assets.delete (+ CSRF)
Documentos: view / upload / replace / delete (permissões específicas)
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_permission, verify_csrf, get_db
from app.core.config import ASSET_DOCUMENTS_DIR
from app.models.auth import AppUser
from app.models.climate_asset import ClimateAsset
from app.models.fire_asset import FireAsset
from app.models.store_document import StoreDocument
from app.models.water_asset import WaterAsset
from app.schemas.assets import (
    AssetStoreDetailResponse, AssetStoreFiltersResponse, AssetStoreOptionResponse, AssetStoreResponse,
    AssetSummaryResponse, ClimateAssetCreate, ClimateAssetResponse, ClimateAssetUpdate,
    FireAssetCreate, FireAssetResponse, FireAssetUpdate,
    StoreDocumentCreate, StoreDocumentResponse, StoreDocumentUpdate,
    WaterAssetCreate, WaterAssetResponse, WaterAssetUpdate,
)
from app.services.assets import (
    create_asset, delete_asset, delete_stored_document, document_response,
    get_asset_summary, get_store, get_store_detail, get_store_filters, list_store_options, list_stores,
    save_document_file, update_asset, update_document_record,
)
from app.services.auth import record_audit

router = APIRouter(prefix="/assets", tags=["Assets"])


def _error(exc: ValueError) -> HTTPException:
    msg = str(exc).lower()
    is_not_found = "não encontrado" in msg or "nao encontrado" in msg or "not found" in msg
    return HTTPException(status_code=404 if is_not_found else 422, detail=str(exc))


def _optional_text(value):
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _optional_date(value, label):
    cleaned = _optional_text(value)
    if cleaned is None:
        return None
    try:
        return date.fromisoformat(cleaned)
    except ValueError as exc:
        raise ValueError(f"{label} inválida.") from exc


# ── Summary/Stores ─────────────────────────────────────────────────────────────

@router.get("/summary", response_model=AssetSummaryResponse,
            dependencies=[Depends(require_permission("assets.view"))])
def asset_summary(db: Session = Depends(get_db)):
    return get_asset_summary(db, sync=True)


def _check_filter_sizes(praca: list[str] | None, store_id: list[int] | None) -> None:
    if (praca and (len(praca) > 100 or any(len(value) > 150 for value in praca))) or (store_id and len(store_id) > 1000):
        raise HTTPException(status_code=422, detail="Filtro grande demais.")


@router.get("/stores", response_model=list[AssetStoreResponse],
            dependencies=[Depends(require_permission("assets.view"))])
def asset_stores(q: str | None = Query(default=None, max_length=150),
                 praca: list[str] | None = Query(default=None),
                 store_id: list[int] | None = Query(default=None),
                 page: int = Query(default=1, ge=1),
                 page_size: int = Query(default=1000, ge=1, le=1000),
                 db: Session = Depends(get_db)):
    _check_filter_sizes(praca, store_id)
    return list_stores(db, q=q, pracas=praca, store_ids=store_id, page=page, page_size=page_size)


@router.get("/stores/filters", response_model=AssetStoreFiltersResponse,
            dependencies=[Depends(require_permission("assets.view"))])
def asset_store_filters(db: Session = Depends(get_db)):
    return get_store_filters(db)


@router.get("/stores/options", response_model=list[AssetStoreOptionResponse],
            dependencies=[Depends(require_permission("assets.view"))])
def asset_store_options(db: Session = Depends(get_db)):
    return list_store_options(db)


@router.get("/stores/{store_id}", response_model=AssetStoreDetailResponse,
            dependencies=[Depends(require_permission("assets.view"))])
def asset_store_detail(store_id: int, db: Session = Depends(get_db)):
    try:
        return get_store_detail(db, store_id)
    except ValueError as exc:
        raise _error(exc) from exc


# ── Climatização ───────────────────────────────────────────────────────────────

@router.get("/stores/{store_id}/climatization", response_model=list[ClimateAssetResponse],
            dependencies=[Depends(require_permission("assets.view"))])
def list_climatization(store_id: int, db: Session = Depends(get_db)):
    get_store(db, store_id)
    return db.scalars(select(ClimateAsset).where(ClimateAsset.store_id == store_id).order_by(ClimateAsset.asset_code)).all()


@router.post("/stores/{store_id}/climatization", response_model=ClimateAssetResponse, status_code=201,
             dependencies=[Depends(require_permission("assets.create")), Depends(verify_csrf)])
def create_climatization(store_id: int, payload: ClimateAssetCreate,
                         user: AppUser = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        asset = create_asset(db, store_id, ClimateAsset, payload, "CLI")
        record_audit(db, user_id=user.id, action="ASSET_CREATE", entity_type="climate_asset",
                     entity_id=str(asset.id), store_id=store_id, new_values={"asset_code": asset.asset_code})
        db.commit()
        return asset
    except ValueError as exc:
        raise _error(exc) from exc


@router.put("/climatization/{asset_id}", response_model=ClimateAssetResponse,
            dependencies=[Depends(require_permission("assets.edit")), Depends(verify_csrf)])
def edit_climatization(asset_id: int, payload: ClimateAssetUpdate,
                       user: AppUser = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        asset = update_asset(db, ClimateAsset, asset_id, payload)
        record_audit(db, user_id=user.id, action="ASSET_UPDATE", entity_type="climate_asset", entity_id=str(asset_id))
        db.commit()
        return asset
    except ValueError as exc:
        raise _error(exc) from exc


@router.delete("/climatization/{asset_id}", status_code=204,
               dependencies=[Depends(require_permission("assets.delete")), Depends(verify_csrf)])
def remove_climatization(asset_id: int, user: AppUser = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        delete_asset(db, ClimateAsset, asset_id)
        record_audit(db, user_id=user.id, action="ASSET_DELETE", entity_type="climate_asset", entity_id=str(asset_id))
        db.commit()
    except ValueError as exc:
        raise _error(exc) from exc


# ── Contra-incêndio ────────────────────────────────────────────────────────────

@router.get("/stores/{store_id}/fire-safety", response_model=list[FireAssetResponse],
            dependencies=[Depends(require_permission("assets.view"))])
def list_fire_safety(store_id: int, db: Session = Depends(get_db)):
    get_store(db, store_id)
    return db.scalars(select(FireAsset).where(FireAsset.store_id == store_id).order_by(FireAsset.asset_code)).all()


@router.post("/stores/{store_id}/fire-safety", response_model=FireAssetResponse, status_code=201,
             dependencies=[Depends(require_permission("assets.create")), Depends(verify_csrf)])
def create_fire_safety(store_id: int, payload: FireAssetCreate,
                       user: AppUser = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        asset = create_asset(db, store_id, FireAsset, payload, "INC")
        record_audit(db, user_id=user.id, action="ASSET_CREATE", entity_type="fire_asset",
                     entity_id=str(asset.id), store_id=store_id, new_values={"asset_code": asset.asset_code})
        db.commit()
        return asset
    except ValueError as exc:
        raise _error(exc) from exc


@router.put("/fire-safety/{asset_id}", response_model=FireAssetResponse,
            dependencies=[Depends(require_permission("assets.edit")), Depends(verify_csrf)])
def edit_fire_safety(asset_id: int, payload: FireAssetUpdate,
                     user: AppUser = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        asset = update_asset(db, FireAsset, asset_id, payload)
        record_audit(db, user_id=user.id, action="ASSET_UPDATE", entity_type="fire_asset", entity_id=str(asset_id))
        db.commit()
        return asset
    except ValueError as exc:
        raise _error(exc) from exc


@router.delete("/fire-safety/{asset_id}", status_code=204,
               dependencies=[Depends(require_permission("assets.delete")), Depends(verify_csrf)])
def remove_fire_safety(asset_id: int, user: AppUser = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        delete_asset(db, FireAsset, asset_id)
        record_audit(db, user_id=user.id, action="ASSET_DELETE", entity_type="fire_asset", entity_id=str(asset_id))
        db.commit()
    except ValueError as exc:
        raise _error(exc) from exc


# ── Sistema hídrico ────────────────────────────────────────────────────────────

@router.get("/stores/{store_id}/water", response_model=list[WaterAssetResponse],
            dependencies=[Depends(require_permission("assets.view"))])
def list_water(store_id: int, db: Session = Depends(get_db)):
    get_store(db, store_id)
    return db.scalars(select(WaterAsset).where(WaterAsset.store_id == store_id).order_by(WaterAsset.asset_code)).all()


@router.post("/stores/{store_id}/water", response_model=WaterAssetResponse, status_code=201,
             dependencies=[Depends(require_permission("assets.create")), Depends(verify_csrf)])
def create_water(store_id: int, payload: WaterAssetCreate,
                 user: AppUser = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        asset = create_asset(db, store_id, WaterAsset, payload, "AGU")
        record_audit(db, user_id=user.id, action="ASSET_CREATE", entity_type="water_asset",
                     entity_id=str(asset.id), store_id=store_id, new_values={"asset_code": asset.asset_code})
        db.commit()
        return asset
    except ValueError as exc:
        raise _error(exc) from exc


@router.put("/water/{asset_id}", response_model=WaterAssetResponse,
            dependencies=[Depends(require_permission("assets.edit")), Depends(verify_csrf)])
def edit_water(asset_id: int, payload: WaterAssetUpdate,
               user: AppUser = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        asset = update_asset(db, WaterAsset, asset_id, payload)
        record_audit(db, user_id=user.id, action="ASSET_UPDATE", entity_type="water_asset", entity_id=str(asset_id))
        db.commit()
        return asset
    except ValueError as exc:
        raise _error(exc) from exc


@router.delete("/water/{asset_id}", status_code=204,
               dependencies=[Depends(require_permission("assets.delete")), Depends(verify_csrf)])
def remove_water(asset_id: int, user: AppUser = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        delete_asset(db, WaterAsset, asset_id)
        record_audit(db, user_id=user.id, action="ASSET_DELETE", entity_type="water_asset", entity_id=str(asset_id))
        db.commit()
    except ValueError as exc:
        raise _error(exc) from exc


# ── Documentos ─────────────────────────────────────────────────────────────────

@router.get("/stores/{store_id}/documents", response_model=list[StoreDocumentResponse],
            dependencies=[Depends(require_permission("documents.view"))])
def list_documents(store_id: int, db: Session = Depends(get_db)):
    get_store(db, store_id)
    return [document_response(item) for item in db.scalars(
        select(StoreDocument).where(StoreDocument.store_id == store_id)
        .order_by(StoreDocument.created_at.desc())).all()]


@router.post("/stores/{store_id}/documents", response_model=StoreDocumentResponse, status_code=201,
             dependencies=[Depends(require_permission("documents.upload")), Depends(verify_csrf)])
async def create_document(
    store_id: int, file: UploadFile = File(...),
    document_type: str = Form(...), custom_document_type: str | None = Form(default=None),
    document_number: str | None = Form(default=None), issue_date: date | None = Form(default=None),
    expiration_date: date | None = Form(default=None), issuer: str | None = Form(default=None),
    notes: str | None = Form(default=None),
    user: AppUser = Depends(get_current_user), db: Session = Depends(get_db),
):
    stored_filename: str | None = None
    try:
        get_store(db, store_id)
        metadata = StoreDocumentCreate(
            document_type=document_type, custom_document_type=custom_document_type,
            document_number=document_number, issue_date=issue_date,
            expiration_date=expiration_date, issuer=issuer, notes=notes,
        )
        stored_filename, mime_type, file_size = await save_document_file(file)
        document = StoreDocument(
            store_id=store_id, **metadata.model_dump(),
            original_filename=file.filename or "documento",
            stored_filename=stored_filename, mime_type=mime_type, file_size=file_size,
        )
        db.add(document)
        db.flush()
        record_audit(db, user_id=user.id, action="DOCUMENT_UPLOAD",
                     entity_type="store_document", entity_id=str(document.id), store_id=store_id,
                     new_values={"document_type": document_type, "filename": file.filename})
        db.commit()
        db.refresh(document)
        return document_response(document)
    except (ValueError, TypeError) as exc:
        db.rollback(); delete_stored_document(stored_filename); raise _error(exc) from exc
    except Exception:
        db.rollback(); delete_stored_document(stored_filename); raise


@router.put("/documents/{document_id}", response_model=StoreDocumentResponse,
            dependencies=[Depends(require_permission("documents.replace")), Depends(verify_csrf)])
async def edit_document(
    document_id: int, document_type: str = Form(...),
    custom_document_type: str = Form(default=""), document_number: str = Form(default=""),
    issue_date: str = Form(default=""), expiration_date: str = Form(default=""),
    issuer: str = Form(default=""), notes: str = Form(default=""),
    file: UploadFile | None = File(default=None),
    user: AppUser = Depends(get_current_user), db: Session = Depends(get_db),
):
    document = db.get(StoreDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    try:
        metadata = StoreDocumentUpdate(
            document_type=document_type,
            custom_document_type=_optional_text(custom_document_type),
            document_number=_optional_text(document_number),
            issue_date=_optional_date(issue_date, "Data de emissão"),
            expiration_date=_optional_date(expiration_date, "Data de validade"),
            issuer=_optional_text(issuer), notes=_optional_text(notes),
        )
        document = await update_document_record(db, document, metadata, file)
        record_audit(db, user_id=user.id, action="DOCUMENT_REPLACE",
                     entity_type="store_document", entity_id=str(document_id), store_id=document.store_id)
        db.commit()
        return document_response(document)
    except (ValueError, TypeError) as exc:
        raise _error(exc) from exc


@router.delete("/documents/{document_id}", status_code=204,
               dependencies=[Depends(require_permission("documents.delete")), Depends(verify_csrf)])
def remove_document(document_id: int, user: AppUser = Depends(get_current_user), db: Session = Depends(get_db)):
    document = db.get(StoreDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    stored_filename = document.stored_filename
    record_audit(db, user_id=user.id, action="DOCUMENT_DELETE",
                 entity_type="store_document", entity_id=str(document_id), store_id=document.store_id,
                 old_values={"filename": document.original_filename})
    db.delete(document)
    db.commit()
    delete_stored_document(stored_filename)


@router.get("/documents/{document_id}/file",
            dependencies=[Depends(require_permission("documents.view"))])
def document_file(document_id: int, download: bool = Query(default=False),
                  user: AppUser = Depends(get_current_user), db: Session = Depends(get_db)):
    document = db.get(StoreDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    path = Path(ASSET_DOCUMENTS_DIR) / document.stored_filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
    record_audit(db, user_id=user.id,
                 action="DOCUMENT_DOWNLOAD" if download else "DOCUMENT_VIEW",
                 entity_type="store_document", entity_id=str(document_id), store_id=document.store_id)
    db.commit()
    return FileResponse(path, media_type=document.mime_type, filename=document.original_filename,
                        content_disposition_type="attachment" if download else "inline")
