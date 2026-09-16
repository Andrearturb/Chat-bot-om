"""
Rotas de verificação da aplicação.

Este módulo define uma rota simples para confirmar se a API está ativa.
"""

from fastapi import APIRouter

from app.core.config import APP_NAME, APP_VERSION

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("")
def health_check() -> dict[str, str]:
    """
    Retorna o status básico da aplicação.
    """
    return {
        "status": "ok",
        "service": APP_NAME,
        "version": APP_VERSION,
    }