"""
POST /imports/tape — requer x-api-key E sync.tape
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_permission, verificar_api_key
from app.db.session import get_db
from app.models.auth import AppUser
from app.schemas.upload import UploadResponse
from app.services.auth import record_audit
from app.services.importer import importar_servicos_tape

router = APIRouter(prefix="/imports", tags=["Imports"])
logger = logging.getLogger(__name__)


@router.post(
    "/tape",
    response_model=UploadResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(verificar_api_key), Depends(require_permission("sync.tape"))],
)
def sincronizar_tape(
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
    app_id: int = Query(57531),
    limit: int = Query(100, ge=1, le=500),
) -> UploadResponse:
    try:
        resultado = importar_servicos_tape(db=db, app_id=app_id, limit=limit)
        record_audit(db, user_id=user.id, action="SYNC_TAPE",
                     entity_type="upload", new_values={"total_rows": resultado.get("total_rows")})
        db.commit()
        return UploadResponse(**resultado)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    except Exception as error:
        logger.exception("Erro ao sincronizar Tape")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Erro ao sincronizar: {type(error).__name__}: {error}") from error
