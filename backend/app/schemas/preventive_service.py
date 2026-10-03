"""Resposta enxuta de chamados preventivos para a Central de Indicadores."""

from datetime import datetime

from pydantic import BaseModel


class PreventiveItemResponse(BaseModel):
    ticket: str
    status: str | None
    raw_status: str | None
    store_name: str | None
    tape_center_record_id: int | None = None
    center_unique_number: int | None = None
    praca: str | None
    category: str | None
    subcategory: str | None
    service_description: str | None
    supplier: str | None
    visit_date: datetime | None
    solution_text: str | None
    analyst_responsible: str | None
    non_approval_reason: str | None
    signature_status: str | None
    signed_pdf_url: str | None
    created_on: datetime | None
    completion_date: datetime | None
    approved_value: float | None
    periodicity: str | None
    due_date: datetime | None
    sla_status: str | None


class PreventiveListResponse(BaseModel):
    dados: list[PreventiveItemResponse]
    upload_data: datetime | None
    pracas: list[str]
