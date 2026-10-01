"""
Gestão de Usuários — consulta somente leitura.

Cadastro, liberação, bloqueio e senhas são feitos no console do Keycloak por um
gestor de acesso. Aqui a lista mostra quem já entrou no Chat-bot O&M, o último
perfil visto e se há sessão ativa.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import require_permission
from app.core.dates import iso_utc
from app.db.session import get_db
from app.models.auth import AppUser, UserSession
from app.services.permissions import primary_profile

router = APIRouter(prefix="/users", tags=["Users"], dependencies=[Depends(require_permission("users.view"))])


@router.get("")
def list_users(db: Session = Depends(get_db)) -> list[dict]:
    now = datetime.utcnow()
    with_session = set(db.scalars(
        select(UserSession.user_id).where(
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
            UserSession.absolute_expires_at > now,
        )
    ).all())
    users = db.scalars(select(AppUser).order_by(AppUser.display_name)).all()
    return [
        {
            "id": user.id,
            "display_name": user.display_name,
            "email": user.email,
            "username": user.username,
            "profile": primary_profile(user.last_profiles or []),
            "profiles": list(user.last_profiles or []),
            "last_seen_at": iso_utc(user.last_seen_at),
            "created_at": iso_utc(user.created_at),
            "active_session": user.id in with_session,
        }
        for user in users
    ]
