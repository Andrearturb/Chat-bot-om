"""Sincronização por diferenças das lojas do app Tape dCentros 30902."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.tape_raw import APP_DCENTROS, DCENTROS_SOURCE_NAME, TapeClient, carregar_token
from app.models.tape_center import TapeCenter
from app.models.upload import Upload
from app.services.importer import _normalizar_para_comparacao, converter_para_brasilia, normalizar_texto


logger = logging.getLogger(__name__)

FIELD_IDS = {
    "name": 280836,
    "short_name": 334477,
    "bcps_number": 334670,
    "sap_number": 334669,
    "cost_center": 522123,
    "business_type": 280859,
    "brand": 280855,
    "company": 280856,
    "cnpj": 281083,
    "uf": 374701,
    "praca": 280858,
    "address": 281074,
    "status": 280852,
    "unique_number": 290650,
}
SYNC_FIELDS = ("title", *FIELD_IDS.keys(), "record_url")


def _first_value(field: dict[str, Any]) -> object | None:
    values = field.get("values") or []
    if not values:
        return None
    value = values[0].get("value") if isinstance(values[0], dict) else values[0]
    if isinstance(value, dict):
        return value.get("text") or value.get("title") or value.get("value")
    return value


def extract_center(record: dict[str, Any]) -> tuple[int, dict[str, Any]] | None:
    try:
        record_id = int(record.get("record_id"))
    except (TypeError, ValueError):
        return None
    title = normalizar_texto(record.get("title"))
    if record_id <= 0 or not title:
        return None

    raw_fields = {
        field.get("field_id"): _first_value(field)
        for field in record.get("fields") or []
        if isinstance(field, dict)
    }
    fields = {
        key: normalizar_texto(raw_fields.get(field_id))
        for key, field_id in FIELD_IDS.items()
        if key != "unique_number"
    }
    raw_number = raw_fields.get(FIELD_IDS["unique_number"])
    try:
        fields["unique_number"] = int(raw_number) if raw_number is not None else None
    except (TypeError, ValueError):
        fields["unique_number"] = None
    fields["title"] = title
    fields["record_url"] = normalizar_texto(record.get("record_url"))
    return record_id, fields


def sync_centers(db: Session, rows: list[dict[str, Any]], upload_id: int,
                 now: datetime) -> dict[str, int]:
    prepared: dict[int, dict[str, Any]] = {}
    rejected = 0
    for row in rows:
        try:
            result = extract_center(row)
            if result is None:
                rejected += 1
            else:
                prepared[result[0]] = result[1]
        except Exception:
            rejected += 1
            logger.exception("Erro ao preparar loja do dCentros")

    if not prepared:
        return {"inserted": 0, "updated": 0, "unchanged": 0, "rejected": rejected}

    existing = {
        item.record_id: item for item in db.execute(
            select(TapeCenter).where(TapeCenter.record_id.in_(prepared))
        ).scalars()
    }
    inserted = updated = unchanged = 0
    for record_id, fields in prepared.items():
        item = existing.get(record_id)
        if item is None:
            db.add(TapeCenter(record_id=record_id, upload_id=upload_id, synced_at=now, **fields))
            inserted += 1
        elif any(
            _normalizar_para_comparacao(getattr(item, key)) != _normalizar_para_comparacao(fields[key])
            for key in SYNC_FIELDS
        ):
            for key in SYNC_FIELDS:
                setattr(item, key, fields[key])
            item.upload_id = upload_id
            item.synced_at = now
            updated += 1
        else:
            item.synced_at = now
            unchanged += 1
    return {"inserted": inserted, "updated": updated, "unchanged": unchanged, "rejected": rejected}


def importar_centros_tape(db: Session, limit: int = 100) -> dict[str, object]:
    with TapeClient(carregar_token()) as tape:
        rows = tape.get_records_by_app(APP_DCENTROS, limit=limit)["records"]
    if not rows:
        return {
            "message": "Coleta retornou 0 registros. Banco preservado sem alterações.",
            "total_rows": 0, "inserted": 0, "updated": 0, "unchanged": 0,
            "rejected": 0, "upload_data": None, "source_file_name": DCENTROS_SOURCE_NAME,
        }

    upload = Upload(source_file_name=DCENTROS_SOURCE_NAME, total_rows=0)
    try:
        db.add(upload)
        db.flush()
        counts = sync_centers(db, rows, upload.id, datetime.now(timezone.utc))
        upload.total_rows = counts["inserted"] + counts["updated"] + counts["unchanged"]
        upload.inserted_count = counts["inserted"]
        upload.updated_count = counts["updated"]
        upload.unchanged_count = counts["unchanged"]
        upload.rejected_count = counts["rejected"]
        db.commit()
        db.refresh(upload)
    except Exception:
        db.rollback()
        raise

    return {
        "message": "Sincronização do dCentros concluída com sucesso.",
        "total_rows": upload.total_rows,
        **counts,
        "upload_data": converter_para_brasilia(upload.uploaded_at),
        "source_file_name": DCENTROS_SOURCE_NAME,
    }
