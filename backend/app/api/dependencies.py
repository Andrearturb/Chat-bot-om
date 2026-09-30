"""
Dependências compartilhadas da API.
"""

from __future__ import annotations

import secrets

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import API_KEY, INTERNAL_API_KEY, SESSION_COOKIE_NAME
from app.db.session import get_db
from app.models.auth import AppUser, UserSession
from app.services.auth import get_session, record_security_event, touch_session
from app.services.session_refresh import SessionRevoked, ensure_fresh_snapshot


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


def get_valid_session(request: Request, db: Session = Depends(get_db)) -> UserSession:
    """Sessão válida pelo cookie, sem renovar o retrato (logout e CSRF)."""
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Não autenticado.")
    session = get_session(db, token)
    if session is None:
        record_security_event(
            db,
            event_type="SESSION_EXPIRED",
            severity="low",
            metadata={"path": str(request.url.path)},
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sessão expirada ou inválida.")
    return session


def get_current_session(
    session: UserSession = Depends(get_valid_session),
    db: Session = Depends(get_db),
) -> UserSession:
    """Sessão com o retrato de acesso em dia (renovado no Keycloak a cada 5 min)."""
    try:
        session = ensure_fresh_snapshot(db, session)
    except SessionRevoked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão encerrada. Entre novamente.",
        ) from None
    touch_session(db, session)
    return session


def get_current_user(
    session: UserSession = Depends(get_current_session),
    db: Session = Depends(get_db),
) -> AppUser:
    user = db.get(AppUser, session.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuário não encontrado.")
    return user


# ─── Permissões ───────────────────────────────────────────────────────────────

def require_permission(permission_code: str):
    """
    Factory de dependência. A permissão vem do retrato da sessão, isto é, dos
    papéis do client chat-bot-om-bff no token assinado pelo Keycloak.

    Uso:
        @router.get("/...", dependencies=[Depends(require_permission("assets.view"))])
    """
    def _checker(
        request: Request,
        session: UserSession = Depends(get_current_session),
        db: Session = Depends(get_db),
    ) -> None:
        if permission_code not in (session.permissions or []):
            record_security_event(
                db,
                event_type="ACCESS_DENIED",
                severity="medium",
                user_id=session.user_id,
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
    session: UserSession = Depends(get_valid_session),
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
