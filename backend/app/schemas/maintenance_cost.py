"""Linhas FBL3N lidas pela Central de Indicadores."""

from datetime import date, datetime

from pydantic import BaseModel


class MaintenanceCostItemResponse(BaseModel):
    id: int
    conta_razao: str
    posting_date: date
    document_date: date | None
    document_number: str | None
    posting_key: str | None
    document_type: str | None
    amount: float
    division: str | None
    cost_center: str
    tape_center_record_id: int | None
    attribution_source: str | None
    store_name: str | None
    praca: str | None
    supplier_name: str | None
    description: str | None


class MaintenanceCostListResponse(BaseModel):
    dados: list[MaintenanceCostItemResponse]
    upload_data: datetime | None
