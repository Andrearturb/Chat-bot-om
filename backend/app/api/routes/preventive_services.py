"""GET /preventive-services — app Tape 57532, requer indicators.view."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, require_permission
from app.api.routes.services import converter_para_brasilia
from app.integrations.tape_raw import PREVENTIVE_SOURCE_NAME
from app.models.preventive_service import PreventiveService
from app.models.upload import Upload
from app.schemas.preventive_service import PreventiveItemResponse, PreventiveListResponse
from app.services.preventive_importer import normalizar_status_preventivo


router = APIRouter(prefix="/preventive-services", tags=["Preventive Services"])


@router.get("", response_model=PreventiveListResponse,
            dependencies=[Depends(require_permission("indicators.view"))])
def listar_preventivas(db: Session = Depends(get_db)) -> PreventiveListResponse:
    services = db.query(PreventiveService).order_by(PreventiveService.ticket).all()
    upload = db.query(Upload).filter(
        Upload.source_file_name == PREVENTIVE_SOURCE_NAME
    ).order_by(Upload.uploaded_at.desc()).first()
    dados = [
        PreventiveItemResponse(
            ticket=item.ticket,
            status=normalizar_status_preventivo(item.status),
            raw_status=item.status,
            store_name=item.store_name,
            praca=item.praca,
            category=item.category,
            subcategory=item.subcategory,
            service_description=item.service_description,
            supplier=item.supplier,
            visit_date=item.visit_date,
            solution_text=item.solution_text,
            analyst_responsible=item.analyst_responsible,
            non_approval_reason=item.non_approval_reason,
            signature_status=item.signature_status,
            signed_pdf_url=item.signed_pdf_url,
            created_on=item.created_on,
            completion_date=item.completion_date,
            approved_value=float(item.approved_value) if item.approved_value is not None else None,
            periodicity=item.periodicity,
            due_date=item.due_date,
            sla_status=item.sla_status,
        ) for item in services
    ]
    return PreventiveListResponse(
        dados=dados,
        upload_data=converter_para_brasilia(upload.uploaded_at) if upload else None,
        pracas=sorted({item.praca for item in services if item.praca}),
    )
