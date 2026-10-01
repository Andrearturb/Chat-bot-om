"""
Renovação do retrato de acesso da sessão.

A cada OIDC_TOKEN_REFRESH_SECONDS o backend usa o refresh token (cifrado na
sessão) para obter novos tokens do Keycloak e atualizar permissões e perfis.
Uma trava por sessão (SELECT ... FOR UPDATE SKIP LOCKED) garante que o refresh
token, de uso único, seja usado por uma só requisição. Só ela fica com a conexão
do banco ocupada durante a chamada ao Keycloak. As demais não esperam: seguem com
o retrato atual, e ``auth.touch_session`` também usa SKIP LOCKED, então nenhuma
escrita do fluxo normal da requisição aguarda essa linha. (Escritas
incondicionais na sessão, como a revogação por logout, ainda esperam a renovação
terminar, que é limitada pelo timeout HTTP.)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import NoReturn

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dates import utcnow
from app.core import config
from app.models.auth import AppUser, OidcIdentity, UserSession
from app.services import oidc
from app.services.auth import decrypt_secret, encrypt_secret, record_security_event, revoke_session
from app.services.permissions import snapshot_from_roles

logger = logging.getLogger(__name__)

# Keycloak fora do ar: no máximo uma tentativa de renovação a cada 30 s por sessão.
REFRESH_RETRY_SECONDS = 30


class SessionRevoked(Exception):
    """A sessão foi encerrada durante a renovação."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _is_fresh(session: UserSession, now: datetime) -> bool:
    return now - session.snapshot_refreshed_at < timedelta(seconds=config.OIDC_TOKEN_REFRESH_SECONDS)


def _retry_throttled(session: UserSession, now: datetime) -> bool:
    return (session.refresh_failed_since is not None and session.refresh_attempted_at is not None
            and now - session.refresh_attempted_at < timedelta(seconds=REFRESH_RETRY_SECONDS))


def _end_session(db: Session, session: UserSession, reason: str) -> None:
    """Revoga a sessão e registra o evento. O commit libera a trava da linha."""
    revoke_session(db, session)
    record_security_event(
        db,
        event_type="ACCESS_REMOVED" if reason == "access_removed" else "SESSION_REVOKED",
        severity="medium",
        user_id=session.user_id,
        metadata={"reason": reason},
    )
    db.commit()


def _revoke(db: Session, session: UserSession, reason: str) -> NoReturn:
    _end_session(db, session, reason)
    raise SessionRevoked(reason)


def _enforce_grace(db: Session, session: UserSession, now: datetime) -> None:
    started = session.refresh_failed_since
    if started is not None and now - started >= timedelta(minutes=config.OIDC_OFFLINE_GRACE_MINUTES):
        _revoke(db, session, "provider_unavailable")


def _lock_statement(session_id: int):
    return (
        select(UserSession)
        .where(UserSession.id == session_id)
        .with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    )


def _lock_session(db: Session, session_id: int) -> UserSession | None:
    """Trava a linha da sessão sem esperar e a recarrega do banco.

    Devolve ``None`` se outra requisição já a travou (está renovando) ou se a linha
    não existe mais. O SQLite ignora FOR UPDATE: lá devolve a linha sempre.
    """
    return db.scalar(_lock_statement(session_id))


def ensure_fresh_snapshot(db: Session, session: UserSession) -> UserSession:
    """Devolve a sessão com o retrato em dia ou levanta ``SessionRevoked``."""
    now = utcnow()
    if _is_fresh(session, now):
        return session
    if _retry_throttled(session, now):
        _enforce_grace(db, session, now)
        return session

    locked = _lock_session(db, session.id)
    if locked is None:
        # Sem a trava: a linha sumiu, foi revogada ou outra requisição está renovando.
        # Nunca esperamos nem falamos com o Keycloak aqui; quem renova atualiza o retrato.
        current = db.get(UserSession, session.id, populate_existing=True)
        gone = current is None or current.revoked_at is not None
        db.commit()  # encerra a transação: não seguramos conexão à toa
        if gone:
            raise SessionRevoked("revoked")
        return current
    if locked.revoked_at is not None:
        db.commit()
        raise SessionRevoked("revoked")
    if _is_fresh(locked, now):
        db.commit()  # outra requisição renovou entre a leitura e a trava: libera a trava
        return locked
    if _retry_throttled(locked, now):
        _enforce_grace(db, locked, now)
        db.commit()
        return locked

    refresh_token = decrypt_secret(locked.refresh_token_enc)
    subject = db.scalar(
        select(OidcIdentity.subject)
        .where(OidcIdentity.user_id == locked.user_id, OidcIdentity.issuer == oidc.issuer())
    )
    if not refresh_token or not subject:
        _revoke(db, locked, "refresh_token_missing")

    try:
        tokens = oidc.refresh(refresh_token, expected_sub=subject)
    except oidc.OidcUnavailable:
        locked.refresh_failed_since = locked.refresh_failed_since or now
        locked.refresh_attempted_at = now
        _enforce_grace(db, locked, now)
        db.commit()
        logger.warning("SESSÃO %s: Keycloak indisponível; retrato atual mantido.", locked.id)
        return locked
    except oidc.OidcError as exc:
        _revoke(db, locked, exc.code)

    # O provedor pode manter o refresh token atual sem repeti-lo na resposta.
    next_refresh_token = tokens.refresh_token or refresh_token
    snapshot = snapshot_from_roles(oidc.roles_from_access_claims(tokens.access_claims))
    if not snapshot.has_access:
        # Revoga e confirma localmente ANTES da chamada de rede (melhor esforço): a
        # trava da linha é liberada e nenhuma conexão fica presa esperando o Keycloak.
        _end_session(db, locked, "access_removed")
        oidc.revoke_refresh_token(next_refresh_token)
        raise SessionRevoked("access_removed")

    locked.refresh_token_enc = encrypt_secret(next_refresh_token)
    if tokens.id_token:
        locked.id_token_hint = tokens.id_token
    locked.permissions = sorted(snapshot.permissions)
    locked.profiles = list(snapshot.profiles)
    locked.snapshot_refreshed_at = now
    locked.refresh_failed_since = None
    locked.refresh_attempted_at = None
    user = db.get(AppUser, locked.user_id)
    if user is not None:
        user.last_profiles = list(snapshot.profiles)
    db.commit()
    return locked
