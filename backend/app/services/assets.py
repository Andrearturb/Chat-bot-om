from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Any, TypeVar

from fastapi import UploadFile
from sqlalchemy import and_, case, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import ASSET_DOCUMENTS_DIR
from app.models.asset_store import AssetStore
from app.models.climate_asset import ClimateAsset
from app.models.fire_asset import FireAsset
from app.models.service import Service
from app.models.store_document import StoreDocument
from app.models.water_asset import WaterAsset
from app.schemas.assets import (
    AssetStoreResponse,
    ClimateAssetResponse,
    FireAssetResponse,
    WaterAssetResponse,
)

MAX_DOCUMENT_SIZE = 15 * 1024 * 1024
ALLOWED_DOCUMENTS = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}

T = TypeVar("T")


def normalize_key(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "-", normalized.casefold()).strip("-")


def store_key_for(store_name: str, bpcs: str | None, sap: str | None, praca: str | None) -> str:
    if sap:
        return f"sap:{normalize_key(sap)}"
    if bpcs:
        return f"bpcs:{normalize_key(bpcs)}"
    return f"name:{normalize_key(store_name)}:{normalize_key(praca)}"


def _name_alias(store_name: str | None, praca: str | None) -> str | None:
    if not store_name or not normalize_key(store_name):
        return None
    return f"name:{normalize_key(store_name)}:{normalize_key(praca)}"


def _store_aliases(store_name: str | None, bpcs: str | None, sap: str | None, praca: str | None) -> set[str]:
    """Retorna identidades fortes; nome+praça é usado somente como fallback.

    Isso evita fundir duas lojas distintas que por acaso compartilham o mesmo
    nome, mas possuem SAP/BPCS diferentes.
    """
    aliases: set[str] = set()
    if sap and normalize_key(sap):
        aliases.add(f"sap:{normalize_key(sap)}")
    if bpcs and normalize_key(bpcs):
        aliases.add(f"bpcs:{normalize_key(bpcs)}")
    if not aliases:
        name_alias = _name_alias(store_name, praca)
        if name_alias:
            aliases.add(name_alias)
    return aliases


def _source_store_groups(rows: list[tuple[Any, ...]]) -> list[dict[str, Any]]:
    """Agrupa a mesma loja sem fundir lojas fortes apenas pelo nome.

    SAP/BPCS são identidades fortes. Nome+praça só conecta um registro legado
    sem identificadores a um registro mais completo da mesma loja.
    """
    groups: list[dict[str, Any]] = []
    for store_name, bpcs, sap, praca in rows:
        if not store_name:
            continue
        aliases = _store_aliases(store_name, bpcs, sap, praca)
        has_strong = bool(sap or bpcs)
        name_alias = _name_alias(store_name, praca)

        matching = [group for group in groups if group["aliases"] & aliases]
        if not matching and name_alias:
            matching = [
                group
                for group in groups
                if group["name_alias"] == name_alias
                and (not has_strong or not group["has_strong"])
            ]

        if not matching:
            groups.append({
                "aliases": set(aliases),
                "rows": [(store_name, bpcs, sap, praca)],
                "name_alias": name_alias,
                "has_strong": has_strong,
            })
            continue

        base = matching[0]
        base["aliases"].update(aliases)
        base["rows"].append((store_name, bpcs, sap, praca))
        base["has_strong"] = base["has_strong"] or has_strong
        for extra in matching[1:]:
            base["aliases"].update(extra["aliases"])
            base["rows"].extend(extra["rows"])
            base["has_strong"] = base["has_strong"] or extra["has_strong"]
            groups.remove(extra)
    return groups


def _best_source_values(rows: list[tuple[Any, ...]]) -> tuple[str, str | None, str | None, str | None]:
    # Prefere a linha mais completa, especialmente a que já possui SAP.
    preferred = max(
        rows,
        key=lambda row: (
            bool(row[2]),  # SAP
            bool(row[1]),  # BPCS
            bool(row[3]),  # praça
            len(str(row[0] or "")),
        ),
    )
    store_name = preferred[0]
    bpcs = preferred[1] or next((row[1] for row in rows if row[1]), None)
    sap = preferred[2] or next((row[2] for row in rows if row[2]), None)
    praca = preferred[3] or next((row[3] for row in rows if row[3]), None)
    return store_name, bpcs, sap, praca


def _merge_store_records(db: Session, canonical: AssetStore, duplicate: AssetStore) -> None:
    """Move ativos/documentos para a loja canônica antes de remover duplicata."""
    if canonical.id == duplicate.id:
        return
    for model in (ClimateAsset, FireAsset, WaterAsset, StoreDocument):
        db.execute(
            update(model)
            .where(model.store_id == duplicate.id)
            .values(store_id=canonical.id)
        )
    db.delete(duplicate)


def sync_asset_stores(db: Session) -> None:
    """Sincroniza lojas de ``services`` preservando a identidade do inventário.

    A sincronização trata a evolução natural dos dados de loja: uma loja que
    antes possuía somente BPCS e posteriormente recebe SAP continua com o mesmo
    ``asset_stores.id`` e, portanto, mantém todos os ativos já cadastrados.
    Duplicatas antigas também são consolidadas sem apagar seus ativos.
    """
    source_rows = db.execute(
        select(Service.store_name, Service.bpcs_number, Service.sap_number, Service.praca)
        .where(Service.store_name.is_not(None))
        .distinct()
    ).all()

    groups = _source_store_groups(list(source_rows))
    existing_stores = list(db.scalars(select(AssetStore).order_by(AssetStore.id)).all())

    for group in groups:
        store_name, bpcs, sap, praca = _best_source_values(group["rows"])
        aliases = set(group["aliases"])
        desired_key = store_key_for(store_name, bpcs, sap, praca)
        aliases.add(desired_key)

        matches = [
            store
            for store in existing_stores
            if store.store_key in aliases
            or bool(_store_aliases(store.store_name, store.bpcs_number, store.sap_number, store.praca) & aliases)
        ]
        # Se ainda não há correspondência por SAP/BPCS, permite promover um
        # registro legado identificado apenas por nome+praça.
        if not matches:
            source_name_alias = _name_alias(store_name, praca)
            if source_name_alias:
                matches = [
                    store
                    for store in existing_stores
                    if _name_alias(store.store_name, store.praca) == source_name_alias
                ]

        if matches:
            # Preserva o registro mais antigo para manter IDs/relações estáveis.
            canonical = min(matches, key=lambda store: store.id)
            duplicates = [store for store in matches if store.id != canonical.id]
            for duplicate in duplicates:
                _merge_store_records(db, canonical, duplicate)
                if duplicate in existing_stores:
                    existing_stores.remove(duplicate)
            # Libera eventuais store_key conflitantes antes de promover a chave.
            if duplicates:
                db.flush()
        else:
            canonical = AssetStore(store_key=desired_key, store_name=store_name)
            db.add(canonical)
            db.flush()
            existing_stores.append(canonical)

        canonical.store_key = desired_key
        canonical.store_name = store_name
        canonical.bpcs_number = bpcs
        canonical.sap_number = sap
        canonical.praca = praca

    db.commit()


def get_store(db: Session, store_id: int) -> AssetStore:
    store = db.get(AssetStore, store_id)
    if store is None:
        raise ValueError("Loja não encontrada.")
    return store


def _count_map(db: Session, model: type[Any]) -> dict[int, int]:
    rows = db.execute(select(model.store_id, func.count(model.id)).group_by(model.store_id)).all()
    return {store_id: int(count) for store_id, count in rows}


def _document_count_maps(db: Session) -> dict[str, dict[int, int]]:
    today = date.today()
    threshold = today + timedelta(days=60)
    rows = db.execute(
        select(
            StoreDocument.store_id,
            func.count(StoreDocument.id),
            func.sum(
                case(
                    (
                        and_(
                            StoreDocument.expiration_date.is_not(None),
                            StoreDocument.expiration_date >= today,
                            StoreDocument.expiration_date <= threshold,
                        ),
                        1,
                    ),
                    else_=0,
                )
            ),
            func.sum(
                case(
                    (
                        and_(
                            StoreDocument.expiration_date.is_not(None),
                            StoreDocument.expiration_date < today,
                        ),
                        1,
                    ),
                    else_=0,
                )
            ),
        ).group_by(StoreDocument.store_id)
    ).all()
    return {
        "documents": {store_id: int(total or 0) for store_id, total, _, _ in rows},
        "documents_expiring": {store_id: int(expiring or 0) for store_id, _, expiring, _ in rows},
        "documents_expired": {store_id: int(expired or 0) for store_id, _, _, expired in rows},
    }


def _all_count_maps(db: Session) -> dict[str, dict[int, int]]:
    document_counts = _document_count_maps(db)
    return {
        "climate": _count_map(db, ClimateAsset),
        "fire": _count_map(db, FireAsset),
        "water": _count_map(db, WaterAsset),
        **document_counts,
    }


def _document_status(expiration_date: date | None, today: date | None = None) -> str:
    if expiration_date is None:
        return "Sem validade"
    current = today or date.today()
    if expiration_date < current:
        return "Vencido"
    if expiration_date <= current + timedelta(days=60):
        return "Próximo do vencimento"
    return "Válido"


def document_response(document: StoreDocument) -> dict[str, Any]:
    data = {
        "id": document.id,
        "store_id": document.store_id,
        "document_type": document.document_type,
        "custom_document_type": document.custom_document_type,
        "document_number": document.document_number,
        "issue_date": document.issue_date,
        "expiration_date": document.expiration_date,
        "issuer": document.issuer,
        "notes": document.notes,
        "original_filename": document.original_filename,
        "mime_type": document.mime_type,
        "file_size": document.file_size,
        "created_at": document.created_at,
        "updated_at": document.updated_at,
    }
    data["status"] = _document_status(document.expiration_date)
    return data


def store_response(store: AssetStore, counts: dict[str, dict[int, int]]) -> dict[str, Any]:
    return {
        **AssetStoreResponse.model_validate(store).model_dump(),
        "climatization_count": counts["climate"].get(store.id, 0),
        "fire_safety_count": counts["fire"].get(store.id, 0),
        "water_count": counts["water"].get(store.id, 0),
        "documents_count": counts["documents"].get(store.id, 0),
        "documents_expiring_count": counts["documents_expiring"].get(store.id, 0),
        "documents_expired_count": counts["documents_expired"].get(store.id, 0),
    }


def get_asset_summary(db: Session, *, sync: bool = True) -> dict[str, int]:
    if sync:
        sync_asset_stores(db)
    stores_count = db.scalar(select(func.count(AssetStore.id))) or 0
    climate_count = db.scalar(select(func.count(ClimateAsset.id))) or 0
    fire_count = db.scalar(select(func.count(FireAsset.id))) or 0
    water_count = db.scalar(select(func.count(WaterAsset.id))) or 0
    documents_count = db.scalar(select(func.count(StoreDocument.id))) or 0
    return {
        "stores_count": int(stores_count),
        "equipment_count": int(climate_count + fire_count + water_count),
        "documents_count": int(documents_count),
    }


def get_store_filters(db: Session) -> dict[str, list[str]]:
    if (db.scalar(select(func.count(AssetStore.id))) or 0) == 0:
        sync_asset_stores(db)
    values = db.scalars(
        select(AssetStore.praca)
        .where(AssetStore.praca.is_not(None), func.trim(AssetStore.praca) != "")
        .distinct()
        .order_by(AssetStore.praca)
    ).all()
    # A consulta é case-sensitive em alguns bancos; deduplica novamente em Python.
    unique: dict[str, str] = {}
    for value in values:
        if value:
            unique.setdefault(normalize_key(value), value.strip())
    return {"pracas": sorted(unique.values(), key=lambda item: normalize_key(item))}


def _clean_pracas(praca: str | None, pracas: list[str] | None) -> list[str]:
    """Junta a praça única (antiga) com a lista; sem repetição por caixa/espaços."""
    unique: dict[str, str] = {}
    for value in [*(pracas or []), *([praca] if praca else [])]:
        text = (value or "").strip()
        if text:
            unique.setdefault(normalize_key(text), text)
    return list(unique.values())


def apply_store_filters(
    query,
    db: Session,
    *,
    q: str | None = None,
    praca: str | None = None,
    pracas: list[str] | None = None,
    store_ids: list[int] | None = None,
):
    """Filtro único das lojas (lista da tela e exportação).

    Dentro de cada filtro os valores se somam (praça A ou B). Entre filtros, estreita:
    praça marcada E loja marcada E texto da busca.
    """
    if q:
        term = q.strip()
        pattern = f"%{term}%"
        # Use unaccent no PostgreSQL; SQLite usa ilike simples nos testes.
        is_postgres = db.bind.dialect.name == "postgresql" if db.bind else False
        if is_postgres:
            query = query.where(or_(
                func.unaccent(AssetStore.store_name).ilike(func.unaccent(pattern)),
                func.unaccent(AssetStore.bpcs_number).ilike(func.unaccent(pattern)),
                func.unaccent(AssetStore.sap_number).ilike(func.unaccent(pattern)),
                func.unaccent(AssetStore.praca).ilike(func.unaccent(pattern)),
            ))
        else:
            query = query.where(or_(
                AssetStore.store_name.ilike(pattern),
                AssetStore.bpcs_number.ilike(pattern),
                AssetStore.sap_number.ilike(pattern),
                AssetStore.praca.ilike(pattern),
            ))
    selected = _clean_pracas(praca, pracas)
    if selected:
        query = query.where(or_(*[
            func.lower(func.trim(AssetStore.praca)) == func.lower(func.trim(value)) for value in selected
        ]))
    if store_ids:
        query = query.where(AssetStore.id.in_(store_ids))
    return query


def list_stores(
    db: Session,
    q: str | None = None,
    praca: str | None = None,
    page: int = 1,
    page_size: int = 1000,
    *,
    sync: bool = False,
    pracas: list[str] | None = None,
    store_ids: list[int] | None = None,
) -> list[dict[str, Any]]:
    if sync or (db.scalar(select(func.count(AssetStore.id))) or 0) == 0:
        sync_asset_stores(db)
    query = apply_store_filters(
        select(AssetStore).order_by(AssetStore.store_name), db,
        q=q, praca=praca, pracas=pracas, store_ids=store_ids,
    )
    stores = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    counts = _all_count_maps(db)
    return [store_response(store, counts) for store in stores]


def list_store_options(db: Session) -> list[dict[str, Any]]:
    """Lista leve de lojas (sem contagens) para o seletor de Lojas."""
    if (db.scalar(select(func.count(AssetStore.id))) or 0) == 0:
        sync_asset_stores(db)
    stores = db.scalars(select(AssetStore).order_by(AssetStore.store_name)).all()
    return [
        {"id": store.id, "name": store.store_name, "praca": (store.praca or "").strip() or None,
         "bpcs": store.bpcs_number, "sap": store.sap_number}
        for store in stores
    ]


def get_store_detail(db: Session, store_id: int) -> dict[str, Any]:
    store = get_store(db, store_id)
    climatization = db.scalars(
        select(ClimateAsset).where(ClimateAsset.store_id == store_id).order_by(ClimateAsset.asset_code)
    ).all()
    fire_safety = db.scalars(
        select(FireAsset).where(FireAsset.store_id == store_id).order_by(FireAsset.asset_code)
    ).all()
    water = db.scalars(
        select(WaterAsset).where(WaterAsset.store_id == store_id).order_by(WaterAsset.asset_code)
    ).all()
    documents = db.scalars(
        select(StoreDocument).where(StoreDocument.store_id == store_id).order_by(StoreDocument.created_at.desc())
    ).all()

    today = date.today()
    counts = {
        "climate": {store_id: len(climatization)},
        "fire": {store_id: len(fire_safety)},
        "water": {store_id: len(water)},
        "documents": {store_id: len(documents)},
        "documents_expiring": {
            store_id: sum(
                1
                for document in documents
                if document.expiration_date is not None
                and today <= document.expiration_date <= today + timedelta(days=60)
            )
        },
        "documents_expired": {
            store_id: sum(
                1
                for document in documents
                if document.expiration_date is not None and document.expiration_date < today
            )
        },
    }
    return {
        **store_response(store, counts),
        "climatization": [ClimateAssetResponse.model_validate(item).model_dump() for item in climatization],
        "fire_safety": [FireAssetResponse.model_validate(item).model_dump() for item in fire_safety],
        "water": [WaterAssetResponse.model_validate(item).model_dump() for item in water],
        "documents": [document_response(item) for item in documents],
    }


def asset_code(db: Session, store: AssetStore, prefix: str, model: type[Any]) -> str:
    """Gera o próximo código sem reutilizar números após exclusões."""
    identity = normalize_key(store.sap_number or store.bpcs_number or str(store.id))[:30] or str(store.id)
    codes = db.scalars(select(model.asset_code).where(model.store_id == store.id)).all()
    max_sequence = 0
    for code in codes:
        match = re.search(r"-(\d+)$", code or "")
        if match:
            max_sequence = max(max_sequence, int(match.group(1)))
    return f"{prefix}-{identity}-{max_sequence + 1:03d}"


def create_asset(db: Session, store_id: int, model: type[T], payload: Any, prefix: str) -> T:
    payload_data = payload.model_dump()
    # A restrição UNIQUE continua sendo a última barreira para duas criações
    # simultâneas. Em caso de colisão, recalculamos a sequência e tentamos de novo.
    for _ in range(5):
        store = get_store(db, store_id)
        item = model(store_id=store_id, asset_code=asset_code(db, store, prefix, model), **payload_data)
        db.add(item)
        try:
            db.commit()
            db.refresh(item)
            return item
        except IntegrityError:
            db.rollback()
    raise ValueError("Não foi possível gerar um código único para o equipamento. Tente novamente.")


def update_asset(db: Session, model: type[T], asset_id: int, payload: Any) -> T:
    item = db.get(model, asset_id)
    if item is None:
        raise ValueError("Equipamento não encontrado.")

    required_fields = {
        ClimateAsset: {"equipment_type", "capacity_btu", "location", "status"},
        FireAsset: {"equipment_type", "location", "status"},
        WaterAsset: {"equipment_type", "location", "status"},
    }.get(model, set())

    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        if key in required_fields and value is None:
            raise ValueError(f"O campo '{key}' não pode ficar vazio.")
        # Campos opcionais aceitam None para permitir apagar uma informação.
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return item


def delete_asset(db: Session, model: type[T], asset_id: int) -> None:
    item = db.get(model, asset_id)
    if item is None:
        raise ValueError("Equipamento não encontrado.")
    db.delete(item)
    db.commit()


async def save_document_file(file: UploadFile) -> tuple[str, str, int]:
    suffix = Path(file.filename or "").suffix.casefold()
    expected_mime = ALLOWED_DOCUMENTS.get(suffix)
    if expected_mime is None or file.content_type != expected_mime:
        raise ValueError("Arquivo inválido. Aceitos: PDF, JPG, JPEG e PNG.")
    content = await file.read(MAX_DOCUMENT_SIZE + 1)
    if len(content) > MAX_DOCUMENT_SIZE:
        raise ValueError("O arquivo excede o limite de 15 MB.")
    stored_filename = f"{uuid.uuid4().hex}{suffix}"
    directory = Path(ASSET_DOCUMENTS_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / stored_filename).write_bytes(content)
    return stored_filename, expected_mime, len(content)


def delete_stored_document(stored_filename: str | None) -> None:
    if not stored_filename:
        return
    path = Path(ASSET_DOCUMENTS_DIR) / stored_filename
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        # A exclusão física não deve corromper o registro no banco.
        # Um arquivo órfão pode ser limpo administrativamente depois.
        pass


def delete_document_file(document: StoreDocument) -> None:
    delete_stored_document(document.stored_filename)


async def update_document_record(
    db: Session,
    document: StoreDocument,
    metadata: Any,
    file: UploadFile | None = None,
) -> StoreDocument:
    """Atualiza metadados e, opcionalmente, substitui o arquivo com segurança.

    O arquivo antigo só é removido após o commit do novo registro. Se o commit
    falhar, o novo arquivo é limpo e o documento anterior permanece válido.
    """
    new_stored_filename: str | None = None
    old_stored_filename = document.stored_filename
    replacement: tuple[str, str, int] | None = None

    if file is not None and file.filename:
        replacement = await save_document_file(file)
        new_stored_filename = replacement[0]

    try:
        for key, value in metadata.model_dump().items():
            setattr(document, key, value)

        if replacement is not None:
            stored_filename, mime_type, file_size = replacement
            document.original_filename = file.filename or "documento"
            document.stored_filename = stored_filename
            document.mime_type = mime_type
            document.file_size = file_size

        db.commit()
        db.refresh(document)
    except Exception:
        db.rollback()
        delete_stored_document(new_stored_filename)
        raise

    if replacement is not None:
        delete_stored_document(old_stored_filename)
    return document
