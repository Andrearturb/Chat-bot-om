"""
Rotas de autenticação — BFF para o fluxo OIDC com o Keycloak.

O navegador NUNCA recebe access_token nem refresh_token: troca de código,
renovação e revogação acontecem aqui. Perfis e permissões vêm dos papéis do
client chat-bot-om-bff no token assinado.
"""

from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_session, get_current_user, get_valid_session, verify_csrf
from app.core import config
from app.core.config import FRONTEND_ORIGINS, SESSION_COOKIE_NAME, SESSION_COOKIE_SECURE
from app.db.session import get_db
from app.models.auth import AppUser, UserSession
from app.services import oidc
from app.services.auth import (
    check_ai_rate_limit,
    consume_login_request,
    create_login_request,
    create_session,
    decrypt_secret,
    post_logout_redirect_uri,
    record_audit,
    record_security_event,
    revoke_session,
    revoke_sessions_for_logout,
    upsert_user,
)
from app.services.permissions import PROFILE_DISPLAY, primary_profile, snapshot_from_roles

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])

_FRONTEND_ORIGIN = FRONTEND_ORIGINS[0] if FRONTEND_ORIGINS else "http://localhost:5173"
_NO_STORE = {"Cache-Control": "no-store"}

# Prende o state do login ao navegador que o iniciou (proteção contra login CSRF).
LOGIN_BINDING_COOKIE = "om_login_binding"


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
    response.delete_cookie(key=SESSION_COOKIE_NAME, httponly=True, samesite="lax", path="/")


def _set_login_binding_cookie(response: Response, binding: str) -> None:
    response.set_cookie(
        key=LOGIN_BINDING_COOKIE,
        value=binding,
        httponly=True,
        samesite="lax",
        secure=SESSION_COOKIE_SECURE,
        path="/auth",
        max_age=config.OIDC_LOGIN_REQUEST_TTL_SECONDS,
    )


def _login_page_url(auth_error: str | None = None) -> str:
    url = f"{_FRONTEND_ORIGIN.rstrip('/')}/login"
    return f"{url}?auth_error={auth_error}" if auth_error else url


def _redirect_auth_error(code: str) -> RedirectResponse:
    return RedirectResponse(url=_login_page_url(code), status_code=302, headers=_NO_STORE)


def _redirect_denied_after_login(code: str, id_token: str | None) -> RedirectResponse:
    """Encerra a sessão SSO recém-criada no Keycloak e volta para /login?auth_error=<code>.

    Assim a conta autenticada, mas sem papel do app, não fica com sessão pela
    metade e o próximo "Entrar" pede as credenciais de novo.
    """
    target = _login_page_url(code)
    try:
        url = oidc.end_session_url(id_token_hint=id_token, post_logout_redirect_uri=target)
    except oidc.OidcError:
        url = target
    return RedirectResponse(url=url, status_code=302, headers=_NO_STORE)


def _login_failed(db: Session, reason: str, severity: str = "high", **metadata) -> None:
    record_security_event(db, event_type="LOGIN_FAILED", severity=severity,
                          metadata={"reason": reason, **metadata})
    db.commit()


def _start_login(request: Request, db: Session, *, register: bool) -> RedirectResponse:
    if not oidc.is_configured():
        return _redirect_auth_error("provider_unavailable")
    # Reaproveita o vínculo do navegador (abas paralelas compartilham o cookie).
    binding = request.cookies.get(LOGIN_BINDING_COOKIE) or secrets.token_urlsafe(32)
    state, code_verifier, nonce = create_login_request(db, binding=binding)
    try:
        url = oidc.authorization_url(state=state, nonce=nonce, code_verifier=code_verifier, register=register)
    except oidc.OidcError as exc:
        logger.warning("LOGIN: provedor de identidade indisponível (%s).", exc.code)
        return _redirect_auth_error("provider_unavailable")
    response = RedirectResponse(url=url, status_code=302, headers=_NO_STORE)
    _set_login_binding_cookie(response, binding)
    return response


@router.get("/login")
def login(request: Request, db: Session = Depends(get_db)) -> Response:
    """Inicia o login no Keycloak (código + PKCE S256 + nonce)."""
    return _start_login(request, db, register=False)


@router.get("/register")
def register(request: Request, db: Session = Depends(get_db)) -> Response:
    """Abre o autocadastro do Keycloak (prompt=create). A conta nasce sem perfil."""
    return _start_login(request, db, register=True)


@router.get("/callback")
def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
) -> Response:
    """Recebe o código, valida os tokens e, havendo papel do app, cria a sessão."""
    # Uso único, inclusive quando o provedor devolve erro. Só vale no navegador que iniciou o
    # login: sem o cookie de vínculo correto o state é descartado e o callback recusado.
    pending = consume_login_request(db, state, binding=request.cookies.get(LOGIN_BINDING_COOKIE))
    if error:
        logger.warning("CALLBACK: provedor retornou erro: %s", error[:60])
        _login_failed(db, "provider_error", "medium", error=error[:60])
        return _redirect_auth_error("provider_error")
    if pending is None or not code:
        logger.warning("CALLBACK: state inválido, expirado, reutilizado ou de outro navegador.")
        _login_failed(db, "invalid_state")
        return _redirect_auth_error("invalid_state")

    code_verifier, nonce = pending
    try:
        tokens = oidc.exchange_code(code, code_verifier=code_verifier, nonce=nonce)
    except oidc.OidcUnavailable:
        _login_failed(db, "provider_unavailable", "medium")
        return _redirect_auth_error("provider_unavailable")
    except oidc.OidcError as exc:
        logger.warning("CALLBACK: tokens recusados (%s).", exc.code)
        _login_failed(db, "token_exchange_failed", detail=exc.code)
        return _redirect_auth_error("token_exchange")

    snapshot = snapshot_from_roles(oidc.roles_from_access_claims(tokens.access_claims))
    user = upsert_user(db, tokens.access_claims, profiles=snapshot.profiles)
    if not snapshot.has_access:
        record_security_event(db, event_type="LOGIN_DENIED", severity="low", user_id=user.id,
                              metadata={"reason": "not_released"})
        db.commit()
        oidc.revoke_refresh_token(tokens.refresh_token)
        return _redirect_denied_after_login("not_released", tokens.id_token)

    ip = request.client.host if request.client else None
    token = create_session(db, user, tokens=tokens, snapshot=snapshot, ip=ip,
                           ua=request.headers.get("user-agent"))
    record_audit(db, user_id=user.id, action="LOGIN_SUCCESS", entity_type="app_user", entity_id=str(user.id))
    db.commit()

    # O Set-Cookie vai na própria resposta 302 (cookie host-only da origem do frontend).
    # O cookie de vínculo do login não é apagado: abas paralelas ainda precisam dele.
    resp = RedirectResponse(url=_FRONTEND_ORIGIN, status_code=302, headers=_NO_STORE)
    _set_session_cookie(resp, token)
    return resp


@router.get("/me")
def me(
    response: Response,
    session: UserSession = Depends(get_current_session),
    user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Usuário atual, perfis e permissões (retrato vindo do Keycloak) e token CSRF."""
    response.headers.update(_NO_STORE)
    permissions = sorted(session.permissions or [])
    profiles = list(session.profiles or [])
    profile = primary_profile(profiles)
    rate = check_ai_rate_limit(db, user)
    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "display_name": user.display_name,
        "profile": profile,
        "profile_display": PROFILE_DISPLAY.get(profile) if profile else None,
        "profiles": profiles,
        "permissions": permissions,
        "csrf_token": session.csrf_secret,
        "keycloak_console_url": (config.KEYCLOAK_CONSOLE_URL or None) if "users.view" in permissions else None,
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
    response: Response,
    session: UserSession = Depends(get_valid_session),
    db: Session = Depends(get_db),
) -> dict:
    """Revoga a sessão do app e o refresh token no Keycloak; devolve a URL de logout OIDC."""
    response.headers.update(_NO_STORE)
    id_token_hint = session.id_token_hint
    refresh_token = decrypt_secret(session.refresh_token_enc)
    record_audit(db, user_id=session.user_id, action="LOGOUT",
                 entity_type="app_user", entity_id=str(session.user_id))
    revoke_session(db, session)
    db.commit()
    oidc.revoke_refresh_token(refresh_token)
    _clear_session_cookie(response)

    target = post_logout_redirect_uri()
    try:
        logout_url = oidc.end_session_url(id_token_hint=id_token_hint, post_logout_redirect_uri=target)
    except oidc.OidcError:
        logger.warning("LOGOUT: provedor indisponível; retornando direto ao /login.")
        logout_url = target
    return {"logout_url": logout_url}


@router.post("/backchannel-logout")
def backchannel_logout(logout_token: str = Form(default=""), db: Session = Depends(get_db)) -> Response:
    """Keycloak → app: encerra as sessões do ``sid`` (ou, sem sid, todas do ``sub``).

    Chamada servidor a servidor, autenticada pela assinatura do logout token
    (sem cookie nem CSRF). Em produção, o proxy expõe este caminho só para a
    rede do Keycloak.
    """
    try:
        claims = oidc.verify_logout_token(logout_token)
    except oidc.OidcError as exc:
        record_security_event(db, event_type="BACKCHANNEL_LOGOUT_REJECTED", severity="high",
                              metadata={"reason": exc.code})
        db.commit()
        return Response(status_code=400, headers=_NO_STORE)
    revoked = revoke_sessions_for_logout(db, issuer=claims["iss"], sid=claims.get("sid"),
                                         subject=claims.get("sub"))
    record_security_event(db, event_type="BACKCHANNEL_LOGOUT", severity="low", metadata={"sessions": revoked})
    db.commit()
    return Response(status_code=200, headers=_NO_STORE)


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
