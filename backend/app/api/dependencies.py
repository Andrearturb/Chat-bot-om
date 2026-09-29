"""
Dependências compartilhadas da API.
"""

from __future__ import annotations

import secrets

from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import API_KEY, INTERNAL_API_KEY, SESSION_COOKIE_NAME
from app.db.session import get_db
from app.models.auth import AppUser, UserSession
from app.services.auth import (
    check_user_active,
    get_session,
    get_user_permissions,
    record_security_event,
    refresh_session,
)


# ─── API Key legacy (scheduler interno / qa-traces) ──────────────────────────

def verificar_api_key(x_api_key: str = Header(..., alias="x-api-key")) -> None:
    """Valida x-api-key (uso interno/legacy). Tempo constante."""
    if not secrets.compare_digest(x_api_key, API_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key inválida ou ausente.",
        )


# ─── Internal API Key (n8n → backend) ────────────────────────────────────────

def verificar_internal_api_key(
    x_internal_api_key: str = Header(default="", alias="x-internal-api-key"),
) -> None:
    """Valida X-Internal-API-Key para chamadas server-to-server."""
    if not INTERNAL_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Serviço não configurado.",
        )
    if not x_internal_api_key or not secrets.compare_digest(x_internal_api_key, INTERNAL_API_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Chave interna inválida ou ausente.",
        )


# ─── Sessão / usuário autenticado ────────────────────────────────────────────

def _extract_token(request: Request) -> str | None:
    return request.cookies.get(SESSION_COOKIE_NAME)


def get_current_session(
    request: Request,
    db: Session = Depends(get_db),
) -> UserSession:
    token = _extract_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Não autenticado.",
        )
    session = get_session(db, token)
    if session is None:
        record_security_event(
            db,
            event_type="SESSION_EXPIRED",
            severity="low",
            metadata={"path": str(request.url.path)},
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão expirada ou inválida.",
        )
    refresh_session(db, session)
    return session


def get_current_user(
    session: UserSession = Depends(get_current_session),
    db: Session = Depends(get_db),
) -> AppUser:
    user = db.get(AppUser, session.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário não encontrado.",
        )
    ok, reason = check_user_active(user)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=reason,
        )
    return user


# ─── Permissões ───────────────────────────────────────────────────────────────

def require_permission(permission_code: str):
    """
    Factory de dependência.

    Uso:
        @router.get("/...", dependencies=[Depends(require_permission("assets.view"))])
    """
    def _checker(
        request: Request,
        user: AppUser = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> None:
        perms = get_user_permissions(db, user)
        if permission_code not in perms:
            record_security_event(
                db,
                event_type="ACCESS_DENIED",
                severity="medium",
                user_id=user.id,
                metadata={"permission": permission_code, "path": str(request.url.path)},
            )
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permissão necessária: {permission_code}",
            )
    return _checker


# ─── CSRF ─────────────────────────────────────────────────────────────────────

def verify_csrf(
    request: Request,
    x_csrf_token: str = Header(default="", alias="x-csrf-token"),
    session: UserSession = Depends(get_current_session),
    db: Session = Depends(get_db),
) -> None:
    """
    Valida CSRF para métodos mutáveis (POST/PUT/PATCH/DELETE).
    GETs são ignorados.
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    if not secrets.compare_digest(x_csrf_token, session.csrf_secret):
        record_security_event(
            db,
            event_type="CSRF_REJECTED",
            severity="high",
            user_id=session.user_id,
            metadata={"path": str(request.url.path)},
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token CSRF inválido ou ausente.",
        )
