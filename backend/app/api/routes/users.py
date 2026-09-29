"""
Gestão de Acessos — requer users.manage.
Credenciais são responsabilidade do Keycloak, não desta interface.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_permission, verify_csrf
from app.db.session import get_db
from app.models.auth import AppUser, Permission, Profile, UserPermissionOverride
from app.services.auth import get_user_permissions, record_audit, seed_profiles_and_permissions

router = APIRouter(prefix="/users", tags=["Users"],
                   dependencies=[Depends(require_permission("users.manage"))])


class UserListItem(BaseModel):
    id: int
    email: str
    display_name: str
    profile: str | None
    profile_display: str | None
    status: str
    last_seen_at: str | None
    ai_daily_limit: int | None
    ai_per_minute_limit: int | None
    access_expires_at: str | None


def _user_to_item(user: AppUser, db: Session) -> UserListItem:
    profile = db.get(Profile, user.profile_id) if user.profile_id else None
    ai_daily = user.ai_daily_limit_override or (profile.ai_daily_limit if profile else None)
    ai_per_min = user.ai_per_minute_limit_override or (profile.ai_per_minute_limit if profile else None)
    return UserListItem(
        id=user.id, email=user.email, display_name=user.display_name,
        profile=profile.name if profile else None,
        profile_display=profile.display_name if profile else None,
        status=user.status,
        last_seen_at=user.last_seen_at.isoformat() if user.last_seen_at else None,
        ai_daily_limit=ai_daily, ai_per_minute_limit=ai_per_min,
        access_expires_at=user.access_expires_at.isoformat() if user.access_expires_at else None,
    )


def _get_or_404(user_id: int, db: Session) -> AppUser:
    user = db.get(AppUser, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    return user


@router.get("", response_model=list[UserListItem])
def list_users(q: str | None = Query(default=None, max_length=150),
               status_filter: str | None = Query(default=None, alias="status"),
               db: Session = Depends(get_db)) -> list[UserListItem]:
    query = select(AppUser).order_by(AppUser.email)
    if status_filter:
        query = query.where(AppUser.status == status_filter)
    if q:
        q_lower = f"%{q.lower()}%"
        query = query.where(or_(func.lower(AppUser.email).like(q_lower),
                                func.lower(AppUser.display_name).like(q_lower)))
    return [_user_to_item(u, db) for u in db.scalars(query).all()]


@router.get("/profiles")
def list_profiles(db: Session = Depends(get_db)):
    return [{"name": p.name, "display_name": p.display_name}
            for p in db.scalars(select(Profile).order_by(Profile.name)).all()]


@router.get("/{user_id}", response_model=UserListItem)
def get_user(user_id: int, db: Session = Depends(get_db)):
    return _user_to_item(_get_or_404(user_id, db), db)


@router.get("/{user_id}/permissions")
def get_permissions(user_id: int, db: Session = Depends(get_db)) -> dict:
    user = _get_or_404(user_id, db)
    effective = get_user_permissions(db, user)
    overrides = db.scalars(select(UserPermissionOverride).where(UserPermissionOverride.user_id == user_id)).all()
    return {"effective": sorted(effective), "overrides": [
        {"code": db.get(Permission, ov.permission_id).code, "effect": ov.effect}
        for ov in overrides if db.get(Permission, ov.permission_id)]}


@router.put("/{user_id}/profile", dependencies=[Depends(verify_csrf)])
def update_profile(user_id: int, payload: dict,
                   actor: AppUser = Depends(get_current_user), db: Session = Depends(get_db)):
    user = _get_or_404(user_id, db)
    profile = db.scalar(select(Profile).where(Profile.name == payload.get("profile_name", "")))
    if profile is None:
        raise HTTPException(status_code=404, detail="Perfil não encontrado.")
    old = db.get(Profile, user.profile_id).name if user.profile_id else None
    user.profile_id = profile.id
    user.updated_at = datetime.utcnow()
    record_audit(db, user_id=actor.id, action="USER_ROLE_CHANGE",
                 entity_type="app_user", entity_id=str(user_id),
                 old_values={"profile": old}, new_values={"profile": profile.name})
    db.commit()
    return {"ok": True}


@router.put("/{user_id}/status", dependencies=[Depends(verify_csrf)])
def update_status(user_id: int, payload: dict,
                  actor: AppUser = Depends(get_current_user), db: Session = Depends(get_db)):
    user = _get_or_404(user_id, db)
    new_status = payload.get("status")
    if new_status not in ("active", "disabled"):
        raise HTTPException(status_code=422, detail="Status inválido.")
    old = user.status
    user.status = new_status
    user.updated_at = datetime.utcnow()
    record_audit(db, user_id=actor.id,
                 action="USER_ACTIVATE" if new_status == "active" else "USER_DISABLE",
                 entity_type="app_user", entity_id=str(user_id),
                 old_values={"status": old}, new_values={"status": new_status})
    db.commit()
    return {"ok": True}


@router.put("/{user_id}/expiry", dependencies=[Depends(verify_csrf)])
def update_expiry(user_id: int, payload: dict,
                  actor: AppUser = Depends(get_current_user), db: Session = Depends(get_db)):
    user = _get_or_404(user_id, db)
    old = user.access_expires_at.isoformat() if user.access_expires_at else None
    expires_str = payload.get("access_expires_at")
    if expires_str:
        try:
            user.access_expires_at = datetime.fromisoformat(expires_str)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Data inválida.") from exc
    else:
        user.access_expires_at = None
    user.updated_at = datetime.utcnow()
    record_audit(db, user_id=actor.id, action="USER_EXPIRY_CHANGE",
                 entity_type="app_user", entity_id=str(user_id),
                 old_values={"access_expires_at": old},
                 new_values={"access_expires_at": expires_str})
    db.commit()
    return {"ok": True}


@router.put("/{user_id}/ai-limit", dependencies=[Depends(verify_csrf)])
def update_ai_limit(user_id: int, payload: dict,
                    actor: AppUser = Depends(get_current_user), db: Session = Depends(get_db)):
    user = _get_or_404(user_id, db)
    old = {"ai_daily": user.ai_daily_limit_override, "ai_per_min": user.ai_per_minute_limit_override}
    user.ai_daily_limit_override = payload.get("ai_daily_limit")
    user.ai_per_minute_limit_override = payload.get("ai_per_minute_limit")
    user.updated_at = datetime.utcnow()
    record_audit(db, user_id=actor.id, action="USER_AI_LIMIT_CHANGE",
                 entity_type="app_user", entity_id=str(user_id),
                 old_values=old, new_values=payload)
    db.commit()
    return {"ok": True}


@router.post("/{user_id}/permission-overrides", dependencies=[Depends(verify_csrf)], status_code=201)
def add_override(user_id: int, payload: dict,
                 actor: AppUser = Depends(get_current_user), db: Session = Depends(get_db)):
    _get_or_404(user_id, db)
    perm = db.scalar(select(Permission).where(Permission.code == payload.get("permission_code", "")))
    if perm is None:
        raise HTTPException(status_code=404, detail="Permissão não encontrada.")
    effect = payload.get("effect")
    if effect not in ("allow", "deny"):
        raise HTTPException(status_code=422, detail="effect deve ser 'allow' ou 'deny'.")
    existing = db.scalar(select(UserPermissionOverride).where(
        UserPermissionOverride.user_id == user_id, UserPermissionOverride.permission_id == perm.id))
    if existing:
        existing.effect = effect
    else:
        db.add(UserPermissionOverride(user_id=user_id, permission_id=perm.id, effect=effect))
    record_audit(db, user_id=actor.id, action="USER_PERMISSION_OVERRIDE",
                 entity_type="app_user", entity_id=str(user_id),
                 new_values={"permission": perm.code, "effect": effect})
    db.commit()
    return {"ok": True}


@router.delete("/{user_id}/permission-overrides/{permission_code}",
               dependencies=[Depends(verify_csrf)], status_code=204)
def remove_override(user_id: int, permission_code: str,
                    actor: AppUser = Depends(get_current_user), db: Session = Depends(get_db)):
    _get_or_404(user_id, db)
    perm = db.scalar(select(Permission).where(Permission.code == permission_code))
    if perm:
        existing = db.scalar(select(UserPermissionOverride).where(
            UserPermissionOverride.user_id == user_id, UserPermissionOverride.permission_id == perm.id))
        if existing:
            db.delete(existing)
            record_audit(db, user_id=actor.id, action="USER_PERMISSION_OVERRIDE_REMOVED",
                         entity_type="app_user", entity_id=str(user_id),
                         new_values={"permission": permission_code})
            db.commit()
