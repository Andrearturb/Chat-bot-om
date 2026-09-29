"""
GET /health/live  — público, apenas {"status":"ok"}
GET /health       — requer settings.view, expõe detalhes internos
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text

from app.api.dependencies import require_permission
from app.core.config import APP_NAME, APP_VERSION, N8N_HEALTH_URL
from app.db.session import engine

router = APIRouter(prefix="/health", tags=["Health"])
BRASILIA_TZ = ZoneInfo("America/Sao_Paulo")


def _converter_para_brasilia(valor):
    if valor is None:
        return None
    if isinstance(valor, str):
        try:
            valor = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        except ValueError:
            return valor
    if valor.tzinfo is None:
        valor = valor.replace(tzinfo=timezone.utc)
    return valor.astimezone(BRASILIA_TZ).isoformat()


def _database_snapshot() -> dict:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            service_count = connection.execute(text("SELECT COUNT(*) FROM services")).scalar_one()
            last_sync = connection.execute(text("SELECT MAX(uploaded_at) FROM uploads")).scalar_one_or_none()
        return {"status": "ok", "service_count": int(service_count or 0), "last_sync": _converter_para_brasilia(last_sync)}
    except Exception:
        return {"status": "error", "service_count": None, "last_sync": None}


def _n8n_status() -> str:
    try:
        with httpx.Client(timeout=3.0) as client:
            r = client.get(N8N_HEALTH_URL)
        return "ok" if r.status_code == 200 else "error"
    except httpx.HTTPError:
        return "error"


@router.get("/live")
def health_live() -> dict:
    """Liveness probe — PÚBLICO."""
    return {"status": "ok"}


@router.get("", dependencies=[Depends(require_permission("settings.view"))])
def health_check(response: Response) -> dict:
    """Health detalhado — requer settings.view."""
    database = _database_snapshot()
    n8n = _n8n_status()
    tape_sync = "error" if database["status"] != "ok" else ("ok" if database["last_sync"] else "unknown")
    healthy = database["status"] == "ok" and n8n == "ok"
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ok" if healthy else "degraded",
        "service": APP_NAME,
        "version": APP_VERSION,
        "components": {
            "api": {"status": "ok"},
            "database": {"status": database["status"]},
            "n8n": {"status": n8n},
            "tape_sync": {"status": tape_sync},
        },
        "operations": {"service_count": database["service_count"], "last_sync": database["last_sync"]},
    }
