"""
Sessões server-side, identidade local, limites de IA e auditoria.

Quem pode o quê é decidido no Keycloak (papéis do client chat-bot-om-bff). Aqui
guardamos apenas o retrato recebido no token assinado e o refresh token cifrado.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit, urlunsplit

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core import config
from app.models.auth import (
    AiUsage,
    AppUser,
    AuditLog,
    OidcIdentity,
    OidcLoginRequest,
    SecurityEvent,
    UserSession,
)
from app.services.permissions import RoleSnapshot, ai_limits_for

if TYPE_CHECKING:
    from app.services.oidc import TokenSet


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


# ─── Cifra do refresh token ───────────────────────────────────────────────────

def _fernet() -> Fernet:
    if not config.SESSION_ENCRYPTION_KEY:
        raise RuntimeError("SESSION_ENCRYPTION_KEY não configurada.")
    return Fernet(config.SESSION_ENCRYPTION_KEY.encode())


def encrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        return None


# ─── Login em andamento (state / code_verifier / nonce) ───────────────────────

def create_login_request(db: Session, *, binding: str) -> tuple[str, str, str]:
    """Cria o registro de uso único do login. Retorna (state, code_verifier, nonce).

    ``binding`` é um valor aleatório por navegador (o cookie HttpOnly do login):
    guardamos só o hash. Sem esse vínculo o ``state`` valeria em qualquer
    navegador, e um atacante poderia fazer a vítima abrir o callback da conta
    dele (login CSRF) e entrar na sessão do atacante.
    """
    if not binding:
        raise ValueError("binding obrigatório: o login precisa estar preso ao navegador.")
    now = datetime.utcnow()
    db.execute(delete(OidcLoginRequest).where(OidcLoginRequest.expires_at < now))
    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    nonce = secrets.token_urlsafe(32)
    db.add(OidcLoginRequest(
        state_hash=_sha256(state),
        binding_hash=_sha256(binding),
        code_verifier=code_verifier,
        nonce=nonce,
        created_at=now,
        expires_at=now + timedelta(seconds=config.OIDC_LOGIN_REQUEST_TTL_SECONDS),
    ))
    db.commit()
    return state, code_verifier, nonce


def consume_login_request(
    db: Session, state: str | None, *, binding: str | None
) -> tuple[str, str] | None:
    """Apaga o registro do ``state`` numa única instrução (uso único mesmo com
    requisições simultâneas). Retorna (code_verifier, nonce) só se o registro
    ainda é válido **e** ``binding`` é o do navegador que iniciou o login
    (proteção contra login CSRF). O registro é consumido sempre que o ``state``
    existe, mesmo com vínculo errado: um state visto em outro navegador não
    pode ser reaproveitado."""
    if not state:
        return None
    row = db.execute(
        delete(OidcLoginRequest)
        .where(OidcLoginRequest.state_hash == _sha256(state))
        .returning(
            OidcLoginRequest.code_verifier,
            OidcLoginRequest.nonce,
            OidcLoginRequest.binding_hash,
            OidcLoginRequest.expires_at,
        )
    ).first()
    db.commit()
    if row is None or row.expires_at < datetime.utcnow():
        return None
    if not binding or not hmac.compare_digest(row.binding_hash, _sha256(binding)):
        return None
    return row.code_verifier, row.nonce


# ─── Identidade local ─────────────────────────────────────────────────────────

def upsert_user(db: Session, claims: dict, *, profiles: tuple[str, ...] | list[str]) -> AppUser:
    """Localiza ou cria o registro local pela âncora issuer + subject.

    Nunca vincula por e-mail: uma conta recriada no Keycloak (novo subject) vira
    um registro novo, sem herdar conversas nem auditoria do anterior.
    """
    now = datetime.utcnow()
    email = (claims.get("email") or "").strip().lower()
    username = (claims.get("preferred_username") or "").strip().lower() or None
    display_name = (claims.get("name") or username or email or claims["sub"])[:200]

    identity = db.scalar(
        select(OidcIdentity)
        .where(OidcIdentity.issuer == claims["iss"])
        .where(OidcIdentity.subject == claims["sub"])
    )
    if identity is None:
        user = AppUser(email=email, created_at=now)
        db.add(user)
        db.flush()
        identity = OidcIdentity(user_id=user.id, issuer=claims["iss"], subject=claims["sub"],
                                email_at_link=email, created_at=now)
        db.add(identity)
    else:
        user = db.get(AppUser, identity.user_id)

    user.email = email
    user.username = username
    user.display_name = display_name
    user.last_profiles = list(profiles)
    user.last_seen_at = now
    identity.last_seen_at = now
    db.flush()
    return user


# ─── Sessões ──────────────────────────────────────────────────────────────────

def create_session(
    db: Session,
    user: AppUser,
    *,
    tokens: "TokenSet",
    snapshot: RoleSnapshot,
    ip: str | None = None,
    ua: str | None = None,
) -> str:
    """Cria a sessão server-side e devolve o token opaco do cookie (sem commit)."""
    token = secrets.token_urlsafe(32)
    now = datetime.utcnow()
    sid = (tokens.id_claims or {}).get("sid") or tokens.access_claims.get("sid")
    db.add(UserSession(
        user_id=user.id,
        session_token_hash=_sha256(token),
        csrf_secret=secrets.token_urlsafe(32),
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(minutes=config.SESSION_IDLE_TIMEOUT_MINUTES),
        absolute_expires_at=now + timedelta(hours=config.SESSION_ABSOLUTE_TIMEOUT_HOURS),
        ip_hash=_sha256(ip) if ip else None,
        user_agent_hash=_sha256(ua) if ua else None,
        id_token_hint=tokens.id_token,
        sid=sid,
        refresh_token_enc=encrypt_secret(tokens.refresh_token),
        permissions=sorted(snapshot.permissions),
        profiles=list(snapshot.profiles),
        snapshot_refreshed_at=now,
    ))
    db.flush()
    return token


def get_session(db: Session, token: str) -> UserSession | None:
    session = db.scalar(select(UserSession).where(UserSession.session_token_hash == _sha256(token)))
    if session is None or session.revoked_at is not None:
        return None
    now = datetime.utcnow()
    if now > session.expires_at or now > session.absolute_expires_at:
        return None
    return session


def touch_session(db: Session, session: UserSession) -> None:
    """Atualiza last_seen e a expiração ociosa, no máximo uma vez por minuto."""
    now = datetime.utcnow()
    if (now - session.last_seen_at).total_seconds() > 60:
        session.last_seen_at = now
        session.expires_at = now + timedelta(minutes=config.SESSION_IDLE_TIMEOUT_MINUTES)
        db.commit()


def revoke_session(db: Session, session: UserSession) -> None:
    session.revoked_at = datetime.utcnow()
    session.id_token_hint = None
    session.refresh_token_enc = None
    db.flush()


def revoke_sessions_for_logout(db: Session, *, issuer: str, sid: str | None, subject: str | None) -> int:
    """Backchannel logout: revoga as sessões do ``sid`` (ou, sem sid, todas do ``subject``)."""
    query = select(UserSession).where(UserSession.revoked_at.is_(None))
    if sid:
        query = query.where(UserSession.sid == sid)
    else:
        query = (query.join(OidcIdentity, OidcIdentity.user_id == UserSession.user_id)
                 .where(OidcIdentity.issuer == issuer, OidcIdentity.subject == subject))
    sessions = db.scalars(query).all()
    for session in sessions:
        revoke_session(db, session)
    return len(sessions)


def post_logout_redirect_uri() -> str:
    """URI de retorno após o logout — sempre a página ``/login`` do frontend."""
    parts = urlsplit(config.OIDC_POST_LOGOUT_REDIRECT_URI)
    if parts.path in ("", "/"):
        parts = parts._replace(path="/login")
    return urlunsplit(parts)


# ─── Limites de IA ────────────────────────────────────────────────────────────

def get_ai_limits(user: AppUser) -> tuple[int, int]:
    """(diário, por minuto): o maior limite entre os perfis vistos no último token."""
    return ai_limits_for(user.last_profiles or [])


def check_ai_rate_limit(db: Session, user: AppUser) -> dict[str, Any]:
    """
    Verifica limites de IA. Retorna:
    {"allowed": bool, "used_today": int, "daily_limit": int,
     "used_this_minute": int, "per_minute_limit": int,
     "resets_at": str, "reason": str | None}
    """
    daily_limit, per_min_limit = get_ai_limits(user)
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    minute_start = now - timedelta(seconds=60)

    def _count(since: datetime) -> int:
        return db.scalar(
            select(func.count(AiUsage.id))
            .where(AiUsage.user_id == user.id)
            .where(AiUsage.created_at >= since)
            .where(AiUsage.status != "error")
        ) or 0

    used_today = _count(today_start)
    used_this_minute = _count(minute_start)
    result = {
        "allowed": True,
        "used_today": used_today,
        "daily_limit": daily_limit,
        "used_this_minute": used_this_minute,
        "per_minute_limit": per_min_limit,
        "resets_at": (today_start + timedelta(days=1)).isoformat(),
        "reason": None,
    }
    if used_today >= daily_limit:
        result.update(allowed=False, reason="daily_limit")
    elif used_this_minute >= per_min_limit:
        result.update(allowed=False, reason="per_minute_limit",
                      resets_at=(now + timedelta(seconds=60)).isoformat())
    return result


# ─── Auditoria ────────────────────────────────────────────────────────────────

def record_audit(
    db: Session,
    *,
    user_id: int | None,
    action: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    store_id: int | None = None,
    old_values: dict | None = None,
    new_values: dict | None = None,
    metadata: dict | None = None,
) -> None:
    db.add(AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        store_id=store_id,
        old_values=old_values,
        new_values=new_values,
        metadata_=metadata,
    ))
    db.flush()


def record_security_event(
    db: Session,
    *,
    event_type: str,
    severity: str = "medium",
    user_id: int | None = None,
    metadata: dict | None = None,
) -> None:
    db.add(SecurityEvent(
        user_id=user_id,
        event_type=event_type,
        severity=severity,
        metadata_=metadata,
    ))
    db.flush()
