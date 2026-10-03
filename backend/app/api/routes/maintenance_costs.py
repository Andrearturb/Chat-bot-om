"""Leitura das partidas FBL3N para o painel de custos."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, require_permission
from app.api.routes.services import converter_para_brasilia
from app.models.maintenance_cost import MaintenanceCost
from app.models.upload import Upload
from app.schemas.maintenance_cost import MaintenanceCostItemResponse, MaintenanceCostListResponse
from app.services.maintenance_costs_importer import COST_SOURCE_TYPE


router = APIRouter(prefix="/maintenance-costs", tags=["Maintenance Costs"])


@router.get("", response_model=MaintenanceCostListResponse,
            dependencies=[Depends(require_permission("indicators.view"))])
def list_maintenance_costs(db: Session = Depends(get_db)) -> MaintenanceCostListResponse:
    rows = db.query(MaintenanceCost).order_by(MaintenanceCost.posting_date.desc(), MaintenanceCost.id.desc()).all()
    upload = db.query(Upload).filter(Upload.source_type == COST_SOURCE_TYPE, Upload.total_rows > 0).order_by(
        Upload.uploaded_at.desc(), Upload.id.desc(),
    ).first()
    return MaintenanceCostListResponse(
        dados=[MaintenanceCostItemResponse(
            id=row.id, conta_razao=row.conta_razao, posting_date=row.posting_date,
            document_date=row.document_date, document_number=row.document_number,
            posting_key=row.posting_key, document_type=row.document_type,
            amount=float(row.amount), division=row.division, cost_center=row.cost_center,
            tape_center_record_id=row.tape_center_record_id,
            attribution_source=row.attribution_source, store_name=row.store_name,
            praca=row.praca, supplier_name=row.supplier_name, description=row.description,
        ) for row in rows],
        upload_data=converter_para_brasilia(upload.uploaded_at) if upload else None,
    )
