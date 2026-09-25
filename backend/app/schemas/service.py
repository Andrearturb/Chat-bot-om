"""
Schemas relacionados aos serviços.

Este módulo define o formato dos dados devolvidos pela API para a
listagem completa de serviços importados.
"""

from datetime import datetime

from pydantic import BaseModel


class ServiceItemResponse(BaseModel):
    """
    Representa um serviço individual devolvido pela API.
    """

    ticket: str
    status: str | None
    store_name: str | None
    bpcs_number: str | None
    sap_number: str | None
    praca: str | None
    service_description: str | None
    supplier: str | None
    visit_date: datetime | None
    in_attendance_date: datetime | None
    solution_text: str | None
    signature_status: str | None
    signed_pdf_url: str | None
    created_on: datetime | None
    completion_date: datetime | None
    requester: str | None
    analyst_responsible: str | None
    non_approval_reason: str | None
    category: str | None
    subcategory: str | None


class ServiceListResponse(BaseModel):
    """
    Representa a resposta completa da rota de listagem de serviços.
    """

    dados: list[ServiceItemResponse]
    upload_data: datetime | None
    pracas: list[str]