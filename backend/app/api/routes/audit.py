"""
GET /audit/logs    — requer audit.view
GET /audit/actions — requer audit.view
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import require_permission
from app.core.dates import iso_utc, parse_api_datetime
from app.db.session import get_db
from app.models.asset_store import AssetStore
from app.models.auth import AuditLog, AppUser

router = APIRouter(prefix="/audit", tags=["Audit"],
                   dependencies=[Depends(require_permission("audit.view"))])


@router.get("/logs")
def list_audit_logs(
    user_id: int | None = Query(default=None),
    action: str | None = Query(default=None, max_length=80),
    entity_type: str | None = Query(default=None, max_length=80),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    query = select(AuditLog).order_by(AuditLog.created_at.desc())
    if user_id is not None:
        query = query.where(AuditLog.user_id == user_id)
    if action:
        query = query.where(AuditLog.action == action.upper())
    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type)
    # O navegador manda o início e o fim do dia local já em UTC ("Z"); o banco guarda UTC sem fuso.
    start, end = parse_api_datetime(date_from), parse_api_datetime(date_to)
    if start is not None:
        query = query.where(AuditLog.created_at >= start)
    if end is not None:
        query = query.where(AuditLog.created_at <= end)

    logs = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    user_ids = {log.user_id for log in logs if log.user_id is not None}
    users_map = {}
    if user_ids:
        for u in db.scalars(select(AppUser).where(AppUser.id.in_(user_ids))):
            users_map[u.id] = u.display_name or u.email
    store_ids = {log.store_id for log in logs if log.store_id is not None}
    stores_map = {}
    if store_ids:
        for store in db.scalars(select(AssetStore).where(AssetStore.id.in_(store_ids))):
            stores_map[store.id] = store.store_name

    return {"page": page, "page_size": page_size, "logs": [
        {"id": log.id, "user_id": log.user_id,
         "user_display": users_map.get(log.user_id) if log.user_id else None,
         "action": log.action, "entity_type": log.entity_type,
         "entity_id": log.entity_id, "store_id": log.store_id,
         "store_name": stores_map.get(log.store_id) if log.store_id else None,
         "old_values": log.old_values, "new_values": log.new_values,
         "metadata": log.metadata_, "created_at": iso_utc(log.created_at)}
        for log in logs]}


@router.get("/actions")
def list_actions(db: Session = Depends(get_db)) -> list[str]:
    return list(db.scalars(select(AuditLog.action).distinct().order_by(AuditLog.action)).all())
