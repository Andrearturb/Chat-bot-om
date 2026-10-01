"""
Gestão de Usuários — consulta somente leitura.

Cadastro, liberação, bloqueio e senhas são feitos no console do Keycloak por um
gestor de acesso. Aqui a lista mostra quem já entrou no Chat-bot O&M, o último
perfil visto e se há sessão ativa.
"""

from __future__ import annotations


from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import require_permission
from app.core.dates import utcnow, iso_utc
from app.db.session import get_db
from app.models.auth import AppUser, UserSession
from app.services.permissions import primary_profile

router = APIRouter(prefix="/users", tags=["Users"], dependencies=[Depends(require_permission("users.view"))])


def _person_key(user: AppUser) -> str:
    """Mesma pessoa = mesmo e-mail. Registro sem e-mail nunca é agrupado."""
    return user.email.strip().lower() if user.email and user.email.strip() else f"id:{user.id}"


def _one_per_person(users: list[AppUser]) -> list[AppUser]:
    """Uma linha por pessoa: o registro visto por último.

    Conta recriada no Keycloak = novo ``subject`` = novo registro (o app nunca vincula por
    e-mail). Os antigos ficam no banco para a auditoria, mas não entram na lista.
    """
    newest: dict[str, AppUser] = {}
    for user in users:
        key = _person_key(user)
        current = newest.get(key)
        if current is None or (user.last_seen_at or user.created_at, user.id) > (current.last_seen_at or current.created_at, current.id):
            newest[key] = user
    keep = {user.id for user in newest.values()}
    return [user for user in users if user.id in keep]


@router.get("")
def list_users(db: Session = Depends(get_db)) -> list[dict]:
    now = utcnow()
    with_session = set(db.scalars(
        select(UserSession.user_id).where(
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
            UserSession.absolute_expires_at > now,
        )
    ).all())
    everyone = db.scalars(select(AppUser).order_by(AppUser.display_name)).all()
    # Sessão ativa em qualquer registro da pessoa: a conta antiga pode ainda estar logada.
    person_has_session: dict[str, bool] = {}
    for user in everyone:
        key = _person_key(user)
        person_has_session[key] = person_has_session.get(key, False) or user.id in with_session
    users = _one_per_person(everyone)
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
            "active_session": person_has_session[_person_key(user)],
        }
        for user in users
    ]
