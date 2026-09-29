"""
Rotas de autenticação — BFF para o fluxo OIDC.

O navegador NUNCA recebe access_token nem refresh_token.
Toda a troca de código acontece server-side.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

logger = logging.getLogger(__name__)
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_current_session, verify_csrf
from app.core.config import (
    OIDC_ISSUER_URL,
    SESSION_COOKIE_NAME,
    SESSION_COOKIE_SECURE,
    OIDC_POST_LOGOUT_REDIRECT_URI,
    FRONTEND_ORIGINS,
)
from app.db.session import get_db
from app.models.auth import AppUser, UserSession
from app.services.auth import (
    check_user_active,
    create_session,
    exchange_code,
    get_authorization_url,
    get_logout_url,
    get_user_permissions,
    get_userinfo,
    get_ai_limits,
    check_ai_rate_limit,
    record_audit,
    record_security_event,
    resolve_or_create_user,
    revoke_session,
    get_session,
)

router = APIRouter(prefix="/auth", tags=["Auth"])

# Armazenamento temporário em memória dos state/verifier para o fluxo PKCE.
# Em produção com múltiplos workers, usar Redis ou PostgreSQL.
_pending_states: dict[str, dict] = {}

_FRONTEND_ORIGIN = FRONTEND_ORIGINS[0] if FRONTEND_ORIGINS else "http://localhost:5173"


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=SESSION_COOKIE_SECURE,
        path="/",
        max_age=None,  # session cookie
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        httponly=True,
        samesite="lax",
        path="/",
    )


def _redirect_auth_error(code: str) -> RedirectResponse:
    resp = RedirectResponse(url=f"{_FRONTEND_ORIGIN}/?auth_error={code}", status_code=302)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@router.get("/login")
def login(request: Request) -> Response:
    """Inicia o fluxo OIDC — redireciona para o Keycloak."""
    if not OIDC_ISSUER_URL:
        raise HTTPException(status_code=503, detail="Provedor de identidade não configurado.")

    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    _pending_states[state] = {"verifier": code_verifier}

    try:
        url = get_authorization_url(state, code_verifier)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Erro ao contatar provedor de identidade.") from exc

    return Response(status_code=302, headers={"Location": url})


@router.get("/callback")
def callback(
    code: str,
    state: str,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    """Recebe o authorization code e cria sessão server-side."""
    pending = _pending_states.pop(state, None)
    if not pending:
        logger.warning("CALLBACK: state inválido ou expirado: %s | states em memória: %s", state[:8], list(_pending_states.keys())[:3])
        record_security_event(db, event_type="LOGIN_FAILED", severity="high",
                              metadata={"reason": "invalid_state"})
        db.commit()
        return _redirect_auth_error("invalid_state")

    try:
        tokens = exchange_code(code, pending["verifier"])
        userinfo = get_userinfo(tokens["access_token"])
    except Exception as exc:
        logger.error("CALLBACK: falha no token exchange: %s", exc, exc_info=True)
        record_security_event(db, event_type="LOGIN_FAILED", severity="high",
                              metadata={"reason": "token_exchange_failed"})
        db.commit()
        return _redirect_auth_error("token_exchange")

    user = resolve_or_create_user(db, userinfo)
    if user is None:
        return _redirect_auth_error("no_user")

    ok, reason = check_user_active(user)
    if not ok:
        code_str = "pending" if user.status == "pending" else "disabled"
        logger.warning("CALLBACK: acesso negado após autenticação: user_id=%s status=%s", user.id, user.status)
        return _redirect_auth_error(code_str)

    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    token = create_session(db, user.id, ip=ip, ua=ua)

    record_audit(db, user_id=user.id, action="LOGIN_SUCCESS",
                 entity_type="app_user", entity_id=str(user.id))
    db.commit()

    # O callback é acessado pelo browser em /auth/callback na origem do frontend
    # (Vite/reverse proxy). O Set-Cookie é definido na própria resposta 302 que
    # retorna ao navegador, criando um cookie host-only para localhost em DEV.
    resp = RedirectResponse(url=_FRONTEND_ORIGIN, status_code=302)
    resp.headers["Cache-Control"] = "no-store"
    _set_session_cookie(resp, token)
    return resp


@router.get("/me")
def me(
    user: AppUser = Depends(get_current_user),
    session: UserSession = Depends(get_current_session),
    db: Session = Depends(get_db),
) -> dict:
    """Retorna dados do usuário atual, permissões e CSRF token."""
    from app.models.auth import Profile
    profile = db.get(Profile, user.profile_id) if user.profile_id else None
    perms = get_user_permissions(db, user)
    daily_limit, per_min_limit = get_ai_limits(db, user)
    rate = check_ai_rate_limit(db, user)

    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "profile": profile.name if profile else None,
        "profile_display": profile.display_name if profile else None,
        "status": user.status,
        "access_expires_at": user.access_expires_at.isoformat() if user.access_expires_at else None,
        "permissions": list(perms),
        "csrf_token": session.csrf_secret,
        "ai_usage": {
            "used_today": rate["used_today"],
            "daily_limit": rate["daily_limit"],
            "remaining": max(0, rate["daily_limit"] - rate["used_today"]),
            "per_minute_limit": rate["per_minute_limit"],
            "used_this_minute": rate["used_this_minute"],
            "resets_at": rate["resets_at"],
        },
    }


@router.post("/logout", dependencies=[Depends(verify_csrf)])
def logout(
    request: Request,
    response: Response,
    user: AppUser = Depends(get_current_user),
    session: UserSession = Depends(get_current_session),
    db: Session = Depends(get_db),
) -> dict:
    """Revoga sessão e redireciona para logout do Keycloak."""
    record_audit(db, user_id=user.id, action="LOGOUT",
                 entity_type="app_user", entity_id=str(user.id))
    token = request.cookies.get(SESSION_COOKIE_NAME, "")
    revoke_session(db, token)
    db.commit()
    _clear_session_cookie(response)

    logout_url = get_logout_url() if OIDC_ISSUER_URL else OIDC_POST_LOGOUT_REDIRECT_URI
    return {"logout_url": logout_url}


@router.get("/usage")
def ai_usage(
    user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Retorna sumário de uso da IA do usuário atual."""
    rate = check_ai_rate_limit(db, user)
    return {
        "used_today": rate["used_today"],
        "daily_limit": rate["daily_limit"],
        "remaining": max(0, rate["daily_limit"] - rate["used_today"]),
        "resets_at": rate["resets_at"],
    }
