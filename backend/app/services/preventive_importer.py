"""Sincronização por diferenças do app Tape 57532 em tabela própria."""

from __future__ import annotations

import html
import logging
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.preventive_fields import PREVENTIVE_FIELD_ALIASES, PREVENTIVE_REFERENCE_FIELDS
from app.integrations.tape_raw import (
    APP_MANUTENCOES_PREVENTIVAS, PREVENTIVE_SOURCE_NAME, TapeClient, carregar_token,
)
from app.models.preventive_service import PreventiveService
from app.models.upload import Upload
from app.services.importer import (
    _normalizar_para_comparacao,
    converter_data,
    converter_decimal,
    normalizar_praca,
    normalizar_texto,
    obter_dcentro_record_id,
    obter_valor_campo,
    tratar_local_atendimento,
    tratar_status_assinatura,
)


logger = logging.getLogger(__name__)
SYNC_FIELDS = (
    "status", "store_name", "tape_center_record_id", "praca", "category", "subcategory",
    "service_description", "supplier", "visit_date", "solution_text",
    "analyst_responsible", "non_approval_reason", "signature_status",
    "signed_pdf_url", "created_on", "completion_date", "approved_value",
    "periodicity", "due_date", "sla_status",
)


def field(linha: dict[str, Any], alias: str) -> object | None:
    field_id = PREVENTIVE_FIELD_ALIASES[alias]["field_ids"][0]
    return obter_valor_campo(linha, alias, field_id)


def _normalized(value: object) -> str:
    text = normalizar_texto(value) or ""
    return "".join(char for char in unicodedata.normalize("NFKD", text.lower())
                   if not unicodedata.combining(char))


def normalizar_status_preventivo(value: object) -> str | None:
    text = normalizar_texto(value)
    if _normalized(text) in {"servico finalizado", "servico concluido"}:
        return "Concluído"
    return text


def classificar_sla(value: object) -> str | None:
    """Só classifica quando a Tape declara explicitamente atraso ou prazo.

    O campo 676271 atualmente é uma barra de progresso sem essa informação.
    """
    if value is None:
        return None
    clean = re.sub(r"<[^>]+>", " ", html.unescape(str(value)))
    text = _normalized(clean)
    # Igualdade com o texto inteiro, não busca de palavra — "nao atrasado"
    # contém a palavra "atrasado", mas quer dizer o oposto. Como a regra é só
    # classificar quando a Tape declarar explicitamente, um texto que não bate
    # exatamente fica None (sem dados) em vez de arriscar inverter o veredito.
    if text == "atrasado":
        return "Atrasado"
    if text == "no prazo":
        return "No prazo"
    return None


def _url_from_text(value: object) -> str | None:
    if value is None:
        return None
    match = re.search(r"https?://[^\s\"'<>]+", html.unescape(str(value)))
    return match.group(0).rstrip(".,;)") if match else None


def extrair_campos_preventivos(linha: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    ticket = normalizar_texto(field(linha, "ticket"))
    if ticket is None:
        ticket = normalizar_texto(linha.get("ticket"))
    if ticket is None:
        return None

    location = tratar_local_atendimento(field(linha, "raw_location"))["store_name"]
    store = normalizar_texto(field(linha, "store_custom")) or location
    signature = tratar_status_assinatura(field(linha, "raw_signature"))
    signature_status = signature["signature_status"]
    order_status = field(linha, "order_status")
    if signature_status is None:
        order_text = _normalized(order_status)
        if "conclu" in order_text or "complet" in order_text:
            signature_status = "completo"
        elif "pend" in order_text:
            signature_status = "pendente"

    pdf_url = signature["signed_pdf_url"]
    if signature_status and ("conclu" in _normalized(signature_status) or "complet" in _normalized(signature_status)):
        pdf_url = pdf_url or _url_from_text(order_status) or _url_from_text(field(linha, "pdf_view"))
    else:
        pdf_url = None

    campos = {
        "status": normalizar_texto(field(linha, "status")),
        "store_name": store,
        "tape_center_record_id": obter_dcentro_record_id(linha, "raw_location", 580460),
        "praca": normalizar_praca(field(linha, "praca")),
        "category": normalizar_texto(field(linha, "category")),
        "subcategory": normalizar_texto(field(linha, "subcategory")),
        "service_description": normalizar_texto(field(linha, "service_description")),
        "supplier": normalizar_texto(field(linha, "supplier")),
        "visit_date": converter_data(field(linha, "visit_date")),
        "solution_text": normalizar_texto(field(linha, "solution_text")),
        "analyst_responsible": normalizar_texto(field(linha, "analyst_responsible")),
        "non_approval_reason": normalizar_texto(field(linha, "non_approval_reason")),
        "signature_status": signature_status,
        "signed_pdf_url": pdf_url,
        "created_on": converter_data(linha.get("created_on")),
        "completion_date": converter_data(field(linha, "completion_date")),
        "approved_value": converter_decimal(field(linha, "approved_value")),
        "periodicity": normalizar_texto(field(linha, "periodicity")),
        "due_date": converter_data(field(linha, "due_date")),
        "sla_status": classificar_sla(field(linha, "sla_progress")),
    }
    return ticket, campos


def sincronizar_preventivas(db: Session, rows: list[dict[str, Any]], upload_id: int,
                           agora: datetime) -> dict[str, int]:
    prepared: dict[str, dict[str, Any]] = {}
    rejected = 0
    for row in rows:
        try:
            result = extrair_campos_preventivos(row)
            if result is None:
                rejected += 1
            else:
                prepared[result[0]] = result[1]
        except Exception:
            rejected += 1
            logger.exception("Erro ao preparar chamado preventivo")

    if not prepared:
        return {"inserted": 0, "updated": 0, "unchanged": 0, "rejected": rejected}

    existing = {
        item.ticket: item for item in db.execute(
            select(PreventiveService).where(PreventiveService.ticket.in_(prepared))
        ).scalars()
    }
    inserted = updated = unchanged = 0
    for ticket, fields in prepared.items():
        item = existing.get(ticket)
        if item is None:
            db.add(PreventiveService(ticket=ticket, upload_id=upload_id, synced_at=agora, **fields))
            inserted += 1
        elif any(
            _normalizar_para_comparacao(getattr(item, key)) != _normalizar_para_comparacao(fields[key])
            for key in SYNC_FIELDS
        ):
            for key in SYNC_FIELDS:
                setattr(item, key, fields[key])
            item.upload_id = upload_id
            item.synced_at = agora
            updated += 1
        else:
            item.synced_at = agora
            unchanged += 1

    return {"inserted": inserted, "updated": updated, "unchanged": unchanged, "rejected": rejected}


def importar_preventivas_tape(db: Session, limit: int = 100) -> dict[str, object]:
    token = carregar_token()
    with TapeClient(token) as tape:
        rows = tape.get_records_tratados(
            app_id=APP_MANUTENCOES_PREVENTIVAS,
            limit=limit,
            reference_fields=PREVENTIVE_REFERENCE_FIELDS,
            field_aliases=PREVENTIVE_FIELD_ALIASES,
        )
    source_name = PREVENTIVE_SOURCE_NAME
    if not rows:
        return {
            "message": "Coleta retornou 0 registros. Banco preservado sem alterações.",
            "total_rows": 0, "inserted": 0, "updated": 0, "unchanged": 0,
            "rejected": 0, "upload_data": None, "source_file_name": source_name,
        }

    upload = Upload(source_file_name=source_name, total_rows=0)
    try:
        db.add(upload)
        db.flush()
        counts = sincronizar_preventivas(db, rows, upload.id, datetime.now(timezone.utc))
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

    from app.services.importer import converter_para_brasilia
    return {
        "message": "Sincronização da Tape concluída com sucesso.",
        "total_rows": upload.total_rows,
        **counts,
        "upload_data": converter_para_brasilia(upload.uploaded_at),
        "source_file_name": source_name,
    }
