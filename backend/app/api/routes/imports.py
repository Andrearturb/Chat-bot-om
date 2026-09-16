"""
Rotas relacionadas à importação de dados.

Este módulo define as rotas responsáveis por:
- sincronizar os dados diretamente da Tape API;
- receber dados estruturados em JSON;
- executar a importação dos dados;
- devolver um resumo do processo.

A importação é protegida por API Key.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import verificar_api_key
from app.db.session import get_db
from app.schemas.upload import UploadResponse
from app.services.importer import importar_servicos_tape

router = APIRouter(prefix="/imports", tags=["Imports"])


@router.post(
    "/tape",
    response_model=UploadResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(verificar_api_key)],
)
def sincronizar_tape(
    db: Session = Depends(get_db),
    app_id: int = Query(57531, description="ID do app na Tape"),
    limit: int = Query(100, ge=1, le=500),
) -> UploadResponse:
    """
    Sincroniza os serviços diretamente da Tape API e persiste no banco.
    """

    try:
        resultado = importar_servicos_tape(
            db=db,
            app_id=app_id,
            limit=limit,
        )

        return UploadResponse(**resultado)

    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error

    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ocorreu um erro ao sincronizar os dados da Tape.",
        ) from error


# The JSON import endpoint was removed in favor of direct Tape synchronization.