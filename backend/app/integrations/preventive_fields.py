"""Campos do app de manutenção preventiva (Tape 57532) usados pelo painel."""

from typing import Any


PREVENTIVE_FIELD_ALIASES: dict[str, dict[str, Any]] = {
    "ticket": {"field_ids": [677154], "labels": ["Ticket"]},
    "status": {"field_ids": [676273], "labels": ["Status"]},
    "raw_location": {"field_ids": [580460], "labels": ["Local de Atendimento"]},
    "praca": {"field_ids": [580462], "labels": ["Praça"]},
    "category": {"field_ids": [580461], "labels": ["Serviço (Categoria)"]},
    "subcategory": {"field_ids": [676274], "labels": ["Subcategoria"]},
    "service_description": {"field_ids": [680431], "labels": ["Descrição do Serviço"]},
    "analyst_responsible": {"field_ids": [676275], "labels": ["Analista Responsável"]},
    "supplier": {"field_ids": [676276], "labels": ["Fornecedor"]},
    "visit_date": {"field_ids": [676278], "labels": ["Data Visita"]},
    "solution_text": {"field_ids": [676282], "labels": ["Solução Aplicada"]},
    "non_approval_reason": {"field_ids": [679853], "labels": ["Motivo de Reprovação"]},
    "raw_signature": {"field_ids": [681369], "labels": ["Status de Assinatura"]},
    "order_status": {"field_ids": [681370], "labels": ["Status da ordem de serviço"]},
    "pdf_view": {"field_ids": [681371], "labels": ["PDF_VIEW"]},
    "completion_date": {"field_ids": [676284], "labels": ["Data de Encerramento"]},
    "approved_value": {"field_ids": [680415], "labels": ["Valor Total"]},
    "periodicity": {"field_ids": [693107], "labels": ["Periocidade"]},
    "due_date": {"field_ids": [676272], "labels": ["Data Prevista"]},
    "sla_progress": {"field_ids": [676271], "labels": ["Progresso SLA"]},
}

PREVENTIVE_REFERENCE_FIELDS = [
    definition["field_ids"][0] for definition in PREVENTIVE_FIELD_ALIASES.values()
]
