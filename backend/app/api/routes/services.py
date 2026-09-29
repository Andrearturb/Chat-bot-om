"""
GET /services — requer indicators.view
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, require_permission
from app.models.service import Service
from app.models.upload import Upload
from app.schemas.service import ServiceItemResponse, ServiceListResponse

router = APIRouter(prefix="/services", tags=["Services"])
BRASILIA_TZ = ZoneInfo("America/Sao_Paulo")


def converter_para_brasilia(valor):
    if valor is None:
        return None
    if valor.tzinfo is None:
        valor = valor.replace(tzinfo=timezone.utc)
    return valor.astimezone(BRASILIA_TZ)


@router.get("", response_model=ServiceListResponse,
            dependencies=[Depends(require_permission("indicators.view"))])
def listar_servicos(db: Session = Depends(get_db)) -> ServiceListResponse:
    services = db.query(Service).order_by(Service.ticket).all()
    ultimo_upload = db.query(Upload).order_by(Upload.uploaded_at.desc()).first()

    dados = [
        ServiceItemResponse(
            ticket=s.ticket, status=s.status, store_name=s.store_name,
            bpcs_number=s.bpcs_number, sap_number=s.sap_number, praca=s.praca,
            service_description=s.service_description, supplier=s.supplier,
            visit_date=s.visit_date, in_attendance_date=s.in_attendance_date,
            solution_text=s.solution_text, signature_status=s.signature_status,
            signed_pdf_url=s.signed_pdf_url, created_on=s.created_on,
            completion_date=s.completion_date, requester=s.requester,
            analyst_responsible=s.analyst_responsible,
            non_approval_reason=s.non_approval_reason,
            category=s.category, subcategory=s.subcategory,
        )
        for s in services
    ]
    pracas = sorted({s.praca for s in services if s.praca})
    upload_data = converter_para_brasilia(ultimo_upload.uploaded_at) if ultimo_upload else None
    return ServiceListResponse(dados=dados, upload_data=upload_data, pracas=pracas)
