from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import ASSET_DOCUMENTS_DIR
from app.db.session import get_db
from app.models.climate_asset import ClimateAsset
from app.models.fire_asset import FireAsset
from app.models.store_document import StoreDocument
from app.models.water_asset import WaterAsset
from app.schemas.assets import (
    AssetStoreDetailResponse,
    AssetStoreFiltersResponse,
    AssetStoreResponse,
    AssetSummaryResponse,
    ClimateAssetCreate,
    ClimateAssetResponse,
    ClimateAssetUpdate,
    FireAssetCreate,
    FireAssetResponse,
    FireAssetUpdate,
    StoreDocumentCreate,
    StoreDocumentResponse,
    StoreDocumentUpdate,
    WaterAssetCreate,
    WaterAssetResponse,
    WaterAssetUpdate,
)
from app.services.assets import (
    create_asset,
    delete_asset,
    delete_stored_document,
    document_response,
    get_asset_summary,
    get_store,
    get_store_detail,
    get_store_filters,
    list_stores,
    save_document_file,
    update_asset,
    update_document_record,
)

router = APIRouter(prefix="/assets", tags=["Assets"])


def _error(exc: ValueError) -> HTTPException:
    msg = str(exc).lower()
    is_not_found = "não encontrado" in msg or "nao encontrado" in msg or "not found" in msg
    return HTTPException(status_code=404 if is_not_found else 422, detail=str(exc))


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _optional_date(value: str | None, label: str) -> date | None:
    cleaned = _optional_text(value)
    if cleaned is None:
        return None
    try:
        return date.fromisoformat(cleaned)
    except ValueError as exc:
        raise ValueError(f"{label} inválida.") from exc


@router.get("/summary", response_model=AssetSummaryResponse)
def asset_summary(db: Session = Depends(get_db)):
    return get_asset_summary(db, sync=True)


@router.get("/stores", response_model=list[AssetStoreResponse])
def asset_stores(
    q: str | None = Query(default=None, max_length=150),
    praca: str | None = Query(default=None, max_length=150),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=1000, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    return list_stores(db, q=q, praca=praca, page=page, page_size=page_size)


@router.get("/stores/filters", response_model=AssetStoreFiltersResponse)
def asset_store_filters(db: Session = Depends(get_db)):
    return get_store_filters(db)


@router.get("/stores/{store_id}", response_model=AssetStoreDetailResponse)
def asset_store_detail(store_id: int, db: Session = Depends(get_db)):
    try:
        return get_store_detail(db, store_id)
    except ValueError as exc:
        raise _error(exc) from exc


@router.get("/stores/{store_id}/climatization", response_model=list[ClimateAssetResponse])
def list_climatization(store_id: int, db: Session = Depends(get_db)):
    from sqlalchemy import select
    get_store(db, store_id)
    return db.scalars(select(ClimateAsset).where(ClimateAsset.store_id == store_id).order_by(ClimateAsset.asset_code)).all()


@router.post("/stores/{store_id}/climatization", response_model=ClimateAssetResponse, status_code=201)
def create_climatization(store_id: int, payload: ClimateAssetCreate, db: Session = Depends(get_db)):
    try:
        return create_asset(db, store_id, ClimateAsset, payload, "CLI")
    except ValueError as exc:
        raise _error(exc) from exc


@router.put("/climatization/{asset_id}", response_model=ClimateAssetResponse)
def edit_climatization(asset_id: int, payload: ClimateAssetUpdate, db: Session = Depends(get_db)):
    try:
        return update_asset(db, ClimateAsset, asset_id, payload)
    except ValueError as exc:
        raise _error(exc) from exc


@router.delete("/climatization/{asset_id}", status_code=204)
def remove_climatization(asset_id: int, db: Session = Depends(get_db)):
    try:
        delete_asset(db, ClimateAsset, asset_id)
    except ValueError as exc:
        raise _error(exc) from exc


@router.get("/stores/{store_id}/fire-safety", response_model=list[FireAssetResponse])
def list_fire_safety(store_id: int, db: Session = Depends(get_db)):
    from sqlalchemy import select
    get_store(db, store_id)
    return db.scalars(select(FireAsset).where(FireAsset.store_id == store_id).order_by(FireAsset.asset_code)).all()


@router.post("/stores/{store_id}/fire-safety", response_model=FireAssetResponse, status_code=201)
def create_fire_safety(store_id: int, payload: FireAssetCreate, db: Session = Depends(get_db)):
    try:
        return create_asset(db, store_id, FireAsset, payload, "INC")
    except ValueError as exc:
        raise _error(exc) from exc


@router.put("/fire-safety/{asset_id}", response_model=FireAssetResponse)
def edit_fire_safety(asset_id: int, payload: FireAssetUpdate, db: Session = Depends(get_db)):
    try:
        return update_asset(db, FireAsset, asset_id, payload)
    except ValueError as exc:
        raise _error(exc) from exc


@router.delete("/fire-safety/{asset_id}", status_code=204)
def remove_fire_safety(asset_id: int, db: Session = Depends(get_db)):
    try:
        delete_asset(db, FireAsset, asset_id)
    except ValueError as exc:
        raise _error(exc) from exc


@router.get("/stores/{store_id}/water", response_model=list[WaterAssetResponse])
def list_water(store_id: int, db: Session = Depends(get_db)):
    from sqlalchemy import select
    get_store(db, store_id)
    return db.scalars(select(WaterAsset).where(WaterAsset.store_id == store_id).order_by(WaterAsset.asset_code)).all()


@router.post("/stores/{store_id}/water", response_model=WaterAssetResponse, status_code=201)
def create_water(store_id: int, payload: WaterAssetCreate, db: Session = Depends(get_db)):
    try:
        return create_asset(db, store_id, WaterAsset, payload, "AGU")
    except ValueError as exc:
        raise _error(exc) from exc


@router.put("/water/{asset_id}", response_model=WaterAssetResponse)
def edit_water(asset_id: int, payload: WaterAssetUpdate, db: Session = Depends(get_db)):
    try:
        return update_asset(db, WaterAsset, asset_id, payload)
    except ValueError as exc:
        raise _error(exc) from exc


@router.delete("/water/{asset_id}", status_code=204)
def remove_water(asset_id: int, db: Session = Depends(get_db)):
    try:
        delete_asset(db, WaterAsset, asset_id)
    except ValueError as exc:
        raise _error(exc) from exc


@router.get("/stores/{store_id}/documents", response_model=list[StoreDocumentResponse])
def list_documents(store_id: int, db: Session = Depends(get_db)):
    from sqlalchemy import select
    get_store(db, store_id)
    return [
        document_response(item)
        for item in db.scalars(
            select(StoreDocument)
            .where(StoreDocument.store_id == store_id)
            .order_by(StoreDocument.created_at.desc())
        ).all()
    ]


@router.post("/stores/{store_id}/documents", response_model=StoreDocumentResponse, status_code=201)
async def create_document(
    store_id: int,
    file: UploadFile = File(...),
    document_type: str = Form(...),
    custom_document_type: str | None = Form(default=None),
    document_number: str | None = Form(default=None),
    issue_date: date | None = Form(default=None),
    expiration_date: date | None = Form(default=None),
    issuer: str | None = Form(default=None),
    notes: str | None = Form(default=None),
    db: Session = Depends(get_db),
):
    stored_filename: str | None = None
    try:
        get_store(db, store_id)
        metadata = StoreDocumentCreate(
            document_type=document_type,
            custom_document_type=custom_document_type,
            document_number=document_number,
            issue_date=issue_date,
            expiration_date=expiration_date,
            issuer=issuer,
            notes=notes,
        )
        stored_filename, mime_type, file_size = await save_document_file(file)
        document = StoreDocument(
            store_id=store_id,
            **metadata.model_dump(),
            original_filename=file.filename or "documento",
            stored_filename=stored_filename,
            mime_type=mime_type,
            file_size=file_size,
        )
        db.add(document)
        db.commit()
        db.refresh(document)
        return document_response(document)
    except (ValueError, TypeError) as exc:
        db.rollback()
        delete_stored_document(stored_filename)
        raise _error(exc) from exc
    except Exception:
        db.rollback()
        delete_stored_document(stored_filename)
        raise


@router.put("/documents/{document_id}", response_model=StoreDocumentResponse)
async def edit_document(
    document_id: int,
    document_type: str = Form(...),
    custom_document_type: str = Form(default=""),
    document_number: str = Form(default=""),
    issue_date: str = Form(default=""),
    expiration_date: str = Form(default=""),
    issuer: str = Form(default=""),
    notes: str = Form(default=""),
    file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
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
            issuer=_optional_text(issuer),
            notes=_optional_text(notes),
        )
        document = await update_document_record(db, document, metadata, file)
        return document_response(document)
    except (ValueError, TypeError) as exc:
        raise _error(exc) from exc


@router.delete("/documents/{document_id}", status_code=204)
def remove_document(document_id: int, db: Session = Depends(get_db)):
    document = db.get(StoreDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    stored_filename = document.stored_filename
    db.delete(document)
    db.commit()
    # Remove o arquivo somente depois do commit para não deixar um registro
    # apontando para um arquivo perdido caso o banco falhe.
    delete_stored_document(stored_filename)


@router.get("/documents/{document_id}/file")
def document_file(document_id: int, download: bool = Query(default=False), db: Session = Depends(get_db)):
    document = db.get(StoreDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    path = Path(ASSET_DOCUMENTS_DIR) / document.stored_filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Arquivo do documento não encontrado.")
    disposition = "attachment" if download else "inline"
    return FileResponse(
        path,
        media_type=document.mime_type,
        filename=document.original_filename,
        content_disposition_type=disposition,
    )
