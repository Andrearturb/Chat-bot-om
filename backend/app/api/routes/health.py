"""
Rotas de verificação da aplicação.

O endpoint consolida a saúde da API, do PostgreSQL e do n8n.
"""

import httpx
from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.core.config import APP_NAME, APP_VERSION, N8N_HEALTH_URL
from app.db.session import engine

router = APIRouter(prefix="/health", tags=["Health"])


def _database_status() -> str:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        return "error"


def _n8n_status() -> str:
    try:
        with httpx.Client(timeout=3.0) as client:
            response = client.get(N8N_HEALTH_URL)
        return "ok" if response.status_code == status.HTTP_200_OK else "error"
    except httpx.HTTPError:
        return "error"


@router.get("")
def health_check(response: Response) -> dict:
    """
    Verifica a infraestrutura necessária para o Gentileza responder.

    - API: se esta rota respondeu, a API está ativa.
    - database: executa ``SELECT 1`` no PostgreSQL da aplicação.
    - n8n: consulta o endpoint de readiness do n8n.

    Retorna HTTP 200 apenas quando todos os componentes estão prontos.
    Caso contrário, retorna HTTP 503 com ``status = degraded``.
    """
    database = _database_status()
    n8n = _n8n_status()
    healthy = database == "ok" and n8n == "ok"

    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ok" if healthy else "degraded",
        "service": APP_NAME,
        "version": APP_VERSION,
        "components": {
            "api": {"status": "ok"},
            "database": {"status": database},
            "n8n": {"status": n8n},
        },
    }
