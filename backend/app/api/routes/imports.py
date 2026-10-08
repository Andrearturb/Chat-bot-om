"""
POST /imports/tape — requer x-api-key E sync.tape
"""

import logging

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_permission, verificar_api_key, verify_csrf
from app.db.session import get_db
from app.models.auth import AppUser
from app.schemas.upload import CentralSyncResponse, TapeSourceSyncResponse, UploadResponse
from app.integrations.tape_raw import APP_DCENTROS, APP_MANUTENCOES_CORRETIVAS, APP_MANUTENCOES_PREVENTIVAS
from app.services.auth import record_audit
from app.services.importer import importar_servicos_tape
from app.services.maintenance_costs_importer import import_maintenance_costs
from app.services.tape_sync_guard import TapeSyncBusyError, tape_sync_guard

router = APIRouter(prefix="/imports", tags=["Imports"])
logger = logging.getLogger(__name__)


@router.post(
    '/tape/central', response_model=CentralSyncResponse,
    dependencies=[Depends(require_permission('sync.tape')), Depends(verify_csrf)],
)
def sincronizar_central(
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> CentralSyncResponse:
    """Browser BFF: session + CSRF; credentials for Tape stay on the server."""
    sources = []
    try:
        with tape_sync_guard():
            for app_id, label in (
                (APP_DCENTROS, 'Cadastro de lojas'),
                (APP_MANUTENCOES_CORRETIVAS, 'Corretivos'),
                (APP_MANUTENCOES_PREVENTIVAS, 'Preventivos'),
            ):
                try:
                    result = UploadResponse(**importar_servicos_tape(db=db, app_id=app_id))
                    source_status = 'success' if result.total_rows else 'empty'
                    record_audit(db, user_id=user.id, action='SYNC_TAPE', entity_type='upload',
                                 new_values={'app_id': app_id, 'total_rows': result.total_rows,
                                             'inserted': result.inserted, 'updated': result.updated,
                                             'status': source_status})
                    db.commit()
                    sources.append(TapeSourceSyncResponse(app_id=app_id, label=label,
                                                         status=source_status, result=result))
                except Exception:
                    db.rollback()
                    logger.exception('Falha na sincronização manual da Tape app %s', app_id)
                    sources.append(TapeSourceSyncResponse(app_id=app_id, label=label, status='error'))
    except TapeSyncBusyError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return CentralSyncResponse(sources=sources)


@router.post(
    "/costs", response_model=UploadResponse,
    dependencies=[Depends(verificar_api_key), Depends(require_permission("sync.tape"))],
)
async def import_costs(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> UploadResponse:
    try:
        content = await file.read(20 * 1024 * 1024 + 1)
        result = import_maintenance_costs(db, content, file.filename or "")
        record_audit(db, user_id=user.id, action="IMPORT_COSTS", entity_type="upload",
                     entity_id=str(result["upload_id"]), new_values={
                         "source_file_name": result["source_file_name"],
                         "total_rows": result["total_rows"], "rejected": result["rejected"],
                     })
        db.commit()
        return UploadResponse(**result)
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    except Exception as error:
        db.rollback()
        logger.exception("Erro ao importar custos")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Erro interno ao importar custos.") from error


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
        with tape_sync_guard():
            resultado = importar_servicos_tape(db=db, app_id=app_id, limit=limit)
            record_audit(db, user_id=user.id, action="SYNC_TAPE",
                         entity_type="upload", new_values={"total_rows": resultado.get("total_rows")})
            db.commit()
            return UploadResponse(**resultado)
    except TapeSyncBusyError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    except Exception as error:
        logger.exception("Erro ao sincronizar Tape")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Erro ao sincronizar: {type(error).__name__}: {error}") from error
