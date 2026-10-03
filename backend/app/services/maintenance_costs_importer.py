"""Importação de partidas FBL3N com atribuição estável por centro de custo."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
import math
from pathlib import PurePath
import unicodedata

import pandas as pd
from openpyxl.utils.datetime import from_excel
from sqlalchemy import and_, extract
from sqlalchemy.orm import Session

from app.models.maintenance_cost import MaintenanceCost
from app.models.tape_center import TapeCenter
from app.models.upload import Upload


COST_SOURCE_TYPE = "maintenance_costs"
REQUIRED_COLUMNS = {
    "conta do razao", "centro custo", "data de lancamento", "montante em moeda interna",
}


def _header(value: object) -> str:
    return " ".join("".join(
        char for char in unicodedata.normalize("NFKD", str(value)) if not unicodedata.combining(char)
    ).lower().split())


def _text(value: object) -> str | None:
    if value is None or value == "" or pd.isna(value):
        return None
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        if value.is_integer():
            return str(int(value))
    result = str(value).strip()
    return result or None


def _date(value: object) -> date | None:
    if value is None or value == "" or pd.isna(value):
        return None
    if isinstance(value, (datetime, date)):
        return value.date() if isinstance(value, datetime) else value
    if isinstance(value, (int, float)):
        try:
            return from_excel(value).date()
        except (AttributeError, ValueError, OverflowError):
            return None
    if isinstance(value, str) and len(value.strip()) == 8 and value.strip().isdigit():
        try:
            return datetime.strptime(value.strip(), "%Y%m%d").date()
        except ValueError:
            return None
    try:
        parsed = pd.to_datetime(str(value).strip(), dayfirst=True, errors="coerce")
        return None if pd.isna(parsed) else parsed.date()
    except (TypeError, ValueError):
        return None


def _amount(value: object) -> Decimal | None:
    raw = _text(value)
    if raw is None:
        return None
    raw = raw.replace("R$", "").replace("\xa0", "").replace(" ", "")
    negative = raw.startswith("-") or (raw.startswith("(") and raw.endswith(")")) or raw.endswith("-")
    raw = raw.strip("()-")
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    try:
        result = Decimal(raw)
    except InvalidOperation:
        return None
    if not result.is_finite():
        return None
    return -result if negative else result


def _unique_center(candidates: list[TapeCenter]) -> TapeCenter | None:
    active = [center for center in candidates if (center.status or "").strip().casefold() != "fechada"]
    if len(active) == 1:
        return active[0]
    if not active and len(candidates) == 1:
        return candidates[0]
    return None


def resolve_center(cost_center: str, centers: list[TapeCenter]) -> tuple[int | None, str | None]:
    """Centro inteiro tem precedência. Ambiguidade nele impede fallback por SAP."""
    exact = [center for center in centers if (center.cost_center or "").strip().upper() == cost_center.upper()]
    if exact:
        chosen = _unique_center(exact)
        return (chosen.record_id, "cost_center") if chosen else (None, None)
    suffix = cost_center[-4:].upper()
    by_sap = [center for center in centers if (center.sap_number or "").strip().upper() == suffix]
    chosen = _unique_center(by_sap)
    return (chosen.record_id, "sap_fallback") if chosen else (None, None)


def import_maintenance_costs(db: Session, content: bytes, filename: str) -> dict:
    """Substitui os meses presentes no arquivo. O chamador confirma ou reverte a transação."""
    if not filename.lower().endswith(".xlsx"):
        raise ValueError("Envie uma planilha .xlsx da FBL3N.")
    if not content or len(content) > 20 * 1024 * 1024:
        raise ValueError("A planilha está vazia ou excede 20 MB.")
    try:
        sheet = pd.read_excel(BytesIO(content), dtype=object, keep_default_na=False)
    except Exception as error:
        raise ValueError("Não foi possível ler a planilha XLSX.") from error
    columns = {_header(column): column for column in sheet.columns}
    missing = REQUIRED_COLUMNS - columns.keys()
    if missing:
        raise ValueError(f"Colunas obrigatórias ausentes: {', '.join(sorted(missing))}.")

    def field(row, name: str):
        column = columns.get(_header(name))
        return row[column] if column is not None else None

    centers = db.query(TapeCenter).all()
    upload = Upload(source_file_name=PurePath(filename.replace("\\", "/")).name[:255],
                    source_type=COST_SOURCE_TYPE, total_rows=0)
    db.add(upload)
    db.flush()

    accepted: list[MaintenanceCost] = []
    periods: set[tuple[str, int, int]] = set()
    rejected = 0
    for _, row in sheet.iterrows():
        account = _text(field(row, "conta do razao"))
        cost_center = _text(field(row, "centro custo"))
        posting_date = _date(field(row, "data de lancamento"))
        amount = _amount(field(row, "montante em moeda interna"))
        if not account or not cost_center or posting_date is None or amount is None:
            rejected += 1
            continue
        center_id, source = resolve_center(cost_center, centers)
        accepted.append(MaintenanceCost(
            upload_id=upload.id, conta_razao=account, posting_date=posting_date,
            document_date=_date(field(row, "data do documento")),
            document_number=_text(field(row, "nº documento")),
            posting_key=_text(field(row, "chave de lancamento")),
            document_type=_text(field(row, "tipo de documento")),
            amount=amount, division=_text(field(row, "divisao")), cost_center=cost_center,
            tape_center_record_id=center_id, attribution_source=source,
            supplier_name=_text(field(row, "nome 1")), description=_text(field(row, "texto")),
        ))
        periods.add((account, posting_date.year, posting_date.month))

    for account, year, month in periods:
        db.query(MaintenanceCost).filter(and_(
            MaintenanceCost.conta_razao == account,
            extract("year", MaintenanceCost.posting_date) == year,
            extract("month", MaintenanceCost.posting_date) == month,
        )).delete(synchronize_session="fetch")
    db.add_all(accepted)
    upload.total_rows = len(accepted)
    upload.inserted_count = len(accepted)
    upload.rejected_count = rejected
    db.flush()
    return {
        "message": "Custos importados com sucesso.", "total_rows": len(accepted),
        "inserted": len(accepted), "updated": 0, "unchanged": 0,
        "rejected": rejected, "upload_data": upload.uploaded_at,
        "source_file_name": upload.source_file_name, "upload_id": upload.id,
    }
