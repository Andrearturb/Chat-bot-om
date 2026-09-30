"""
Gestão de Usuários — exclusivo para ADMINISTRADOR (validado no backend).

Credenciais continuam sob responsabilidade do Keycloak: o backend chama a
Keycloak Admin API (server-side) e o PostgreSQL guarda perfil, status e dados
complementares. O navegador nunca acessa a Admin API diretamente.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import require_admin, verify_csrf
from app.db.session import get_db
from app.models.auth import AppUser, Permission, UserPermissionOverride
from app.services.auth import get_user_permissions, record_audit
from app.services.keycloak_admin import IdentityAdminError, KeycloakAdminClient, get_identity_admin
from app.services.user_admin import (
    PASSWORD_MIN_LENGTH,
    OperationResult,
    UserAdminError,
    active_admin_ids,
    create_user,
    list_profiles,
    list_users,
    reset_password,
    send_password_email,
    serialize_user,
    update_user,
)

router = APIRouter(prefix="/users", tags=["Users"], dependencies=[Depends(require_admin)])


# ─── Schemas ──────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    display_name: str = Field(max_length=200)
    email: str = Field(max_length=254)
    username: str | None = Field(default=None, max_length=64)
    profile: str = Field(max_length=50)
    status: Literal["active", "disabled"] = "active"
    password_mode: Literal["temporary", "email"] = "temporary"
    # SecretStr evita que a senha apareça em repr/logs. Nunca é persistida.
    temporary_password: SecretStr | None = None


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=200)
    profile: str | None = Field(default=None, max_length=50)
    status: Literal["active", "disabled"] | None = None


class PasswordReset(BaseModel):
    temporary_password: SecretStr


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _error(exc: UserAdminError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message, "code": exc.code, **exc.extra},
    )


def _result(db: Session, result: OperationResult, actor: AppUser, status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"user": serialize_user(db, result.user, actor_id=actor.id), "warnings": result.warnings},
    )


def _get_or_404(user_id: int, db: Session) -> AppUser:
    user = db.get(AppUser, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    return user


def _secret(value: SecretStr | None) -> str | None:
    return value.get_secret_value() if value is not None else None


# ─── Consultas ────────────────────────────────────────────────────────────────

@router.get("")
def get_users(
    q: str | None = Query(default=None, max_length=150),
    status_filter: str | None = Query(default=None, alias="status", max_length=20),
    profile: str | None = Query(default=None, max_length=50),
    actor: AppUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[dict]:
    return list_users(db, actor_id=actor.id, q=q, status=status_filter, profile=profile)


@router.get("/profiles")
def get_profiles(db: Session = Depends(get_db)) -> list[dict]:
    return list_profiles(db)


@router.get("/capabilities")
def get_capabilities(idp: KeycloakAdminClient = Depends(get_identity_admin)) -> dict:
    """O que a integração com o provedor de identidade permite fazer agora."""
    identity_admin = False
    email_actions = False
    if idp.is_configured():
        try:
            email_actions = idp.smtp_configured()
            identity_admin = True
        except IdentityAdminError:
            identity_admin = False
    return {
        "identity_admin": identity_admin,
        "email_actions": email_actions,
        "password_min_length": PASSWORD_MIN_LENGTH,
    }


@router.get("/{user_id}")
def get_user(user_id: int, actor: AppUser = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    return serialize_user(db, _get_or_404(user_id, db), actor_id=actor.id)


@router.get("/{user_id}/permissions")
def get_permissions(user_id: int, db: Session = Depends(get_db)) -> dict:
    user = _get_or_404(user_id, db)
    effective = get_user_permissions(db, user)
    overrides = db.scalars(select(UserPermissionOverride).where(UserPermissionOverride.user_id == user_id)).all()
    return {"effective": sorted(effective), "overrides": [
        {"code": db.get(Permission, ov.permission_id).code, "effect": ov.effect}
        for ov in overrides if db.get(Permission, ov.permission_id)]}


# ─── Cadastro e edição ────────────────────────────────────────────────────────

@router.post("", dependencies=[Depends(verify_csrf)], status_code=201)
def post_user(
    payload: UserCreate,
    actor: AppUser = Depends(require_admin),
    db: Session = Depends(get_db),
    idp: KeycloakAdminClient = Depends(get_identity_admin),
):
    try:
        result = create_user(
            db, idp, actor,
            display_name=payload.display_name,
            email=payload.email,
            username=payload.username,
            profile_name=payload.profile,
            status=payload.status,
            password_mode=payload.password_mode,
            temporary_password=_secret(payload.temporary_password),
        )
    except UserAdminError as exc:
        return _error(exc)
    return _result(db, result, actor, status_code=201)


@router.patch("/{user_id}", dependencies=[Depends(verify_csrf)])
def patch_user(
    user_id: int,
    payload: UserUpdate,
    actor: AppUser = Depends(require_admin),
    db: Session = Depends(get_db),
    idp: KeycloakAdminClient = Depends(get_identity_admin),
):
    user = _get_or_404(user_id, db)
    try:
        result = update_user(
            db, idp, actor, user,
            display_name=payload.display_name,
            profile_name=payload.profile,
            status=payload.status,
        )
    except UserAdminError as exc:
        return _error(exc)
    return _result(db, result, actor)


def _change_status(user_id: int, new_status: str, actor: AppUser, db: Session, idp: KeycloakAdminClient):
    user = _get_or_404(user_id, db)
    try:
        result = update_user(db, idp, actor, user, status=new_status)
    except UserAdminError as exc:
        return _error(exc)
    return _result(db, result, actor)


@router.post("/{user_id}/activate", dependencies=[Depends(verify_csrf)])
def activate_user(user_id: int, actor: AppUser = Depends(require_admin), db: Session = Depends(get_db),
                  idp: KeycloakAdminClient = Depends(get_identity_admin)):
    return _change_status(user_id, "active", actor, db, idp)


@router.post("/{user_id}/deactivate", dependencies=[Depends(verify_csrf)])
def deactivate_user(user_id: int, actor: AppUser = Depends(require_admin), db: Session = Depends(get_db),
                    idp: KeycloakAdminClient = Depends(get_identity_admin)):
    return _change_status(user_id, "disabled", actor, db, idp)


@router.post("/{user_id}/reset-password", dependencies=[Depends(verify_csrf)])
def post_reset_password(
    user_id: int,
    payload: PasswordReset,
    actor: AppUser = Depends(require_admin),
    db: Session = Depends(get_db),
    idp: KeycloakAdminClient = Depends(get_identity_admin),
):
    user = _get_or_404(user_id, db)
    try:
        result = reset_password(db, idp, actor, user, temporary_password=_secret(payload.temporary_password))
    except UserAdminError as exc:
        return _error(exc)
    # A senha nunca é devolvida: apenas o usuário atualizado e avisos.
    return _result(db, result, actor)


@router.post("/{user_id}/password-email", dependencies=[Depends(verify_csrf)])
def post_password_email(
    user_id: int,
    actor: AppUser = Depends(require_admin),
    db: Session = Depends(get_db),
    idp: KeycloakAdminClient = Depends(get_identity_admin),
):
    user = _get_or_404(user_id, db)
    try:
        result = send_password_email(db, idp, actor, user)
    except UserAdminError as exc:
        return _error(exc)
    return _result(db, result, actor)


# ─── Endpoints legados (mantidos, agora com as mesmas proteções) ──────────────

@router.put("/{user_id}/profile", dependencies=[Depends(verify_csrf)])
def update_profile(user_id: int, payload: dict, actor: AppUser = Depends(require_admin),
                   db: Session = Depends(get_db), idp: KeycloakAdminClient = Depends(get_identity_admin)):
    user = _get_or_404(user_id, db)
    try:
        update_user(db, idp, actor, user, profile_name=str(payload.get("profile_name", "")))
    except UserAdminError as exc:
        return _error(exc)
    return {"ok": True}


@router.put("/{user_id}/status", dependencies=[Depends(verify_csrf)])
def update_status(user_id: int, payload: dict, actor: AppUser = Depends(require_admin),
                  db: Session = Depends(get_db), idp: KeycloakAdminClient = Depends(get_identity_admin)):
    user = _get_or_404(user_id, db)
    try:
        update_user(db, idp, actor, user, status=str(payload.get("status", "")))
    except UserAdminError as exc:
        return _error(exc)
    return {"ok": True}


@router.put("/{user_id}/expiry", dependencies=[Depends(verify_csrf)])
def update_expiry(user_id: int, payload: dict,
                  actor: AppUser = Depends(require_admin), db: Session = Depends(get_db)):
    user = _get_or_404(user_id, db)
    old = user.access_expires_at.isoformat() if user.access_expires_at else None
    expires_str = payload.get("access_expires_at")
    if expires_str:
        if user.id == actor.id:
            raise HTTPException(status_code=409, detail="Você não pode definir expiração para a sua própria conta.")
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
                    actor: AppUser = Depends(require_admin), db: Session = Depends(get_db)):
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
                 actor: AppUser = Depends(require_admin), db: Session = Depends(get_db)):
    _get_or_404(user_id, db)
    perm = db.scalar(select(Permission).where(Permission.code == payload.get("permission_code", "")))
    if perm is None:
        raise HTTPException(status_code=404, detail="Permissão não encontrada.")
    effect = payload.get("effect")
    if effect not in ("allow", "deny"):
        raise HTTPException(status_code=422, detail="effect deve ser 'allow' ou 'deny'.")
    if effect == "deny" and perm.code == "users.manage":
        admins = active_admin_ids(db)
        if user_id == actor.id or (user_id in admins and not (admins - {user_id})):
            raise HTTPException(
                status_code=409,
                detail="Esta restrição removeria o último acesso administrativo à Gestão de Usuários.",
            )
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
                    actor: AppUser = Depends(require_admin), db: Session = Depends(get_db)):
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
