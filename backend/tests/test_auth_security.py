"""Sessões, identidade local, registro de login, limites de IA e auditoria (app/services/auth.py)."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import func, select

from app.core.dates import utcnow
from app.core import config
from app.models.auth import (
    AiUsage,
    AppUser,
    AssistantConversation,
    AuditLog,
    OidcIdentity,
    OidcLoginRequest,
    SecurityEvent,
    UserSession,
)
from app.services import auth
from app.services.permissions import snapshot_from_roles
from tests.oidc_fake import ANALISTA, ISSUER, login_tokens


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _claims(sub: str = "sub-1", email: str | None = "pessoa@exemplo.local", **extra) -> dict:
    return {"iss": ISSUER, "sub": sub, "email": email, "preferred_username": "pessoa",
            "name": "Pessoa Teste", **extra}


def _user(db, sub: str = "sub-1", email: str | None = "pessoa@exemplo.local", profiles=("ANALISTA",)) -> AppUser:
    user = auth.upsert_user(db, _claims(sub, email), profiles=profiles)
    db.commit()
    return user


def _session(db, provider, *, sub: str = "sub-1", roles=ANALISTA, sid: str | None = None):
    user = _user(db, sub=sub)
    tokens = login_tokens(provider, sub, roles, sid=sid)
    token = auth.create_session(db, user, tokens=tokens, snapshot=snapshot_from_roles(roles))
    db.commit()
    session = db.scalar(select(UserSession).where(UserSession.session_token_hash == _sha256(token)))
    return user, token, session


# ── Sessão ────────────────────────────────────────────────────────────────────

def test_token_da_sessao_guardado_somente_como_hash(db, provider):
    _, token, session = _session(db, provider)
    assert session.session_token_hash == _sha256(token)
    assert token not in (session.session_token_hash, session.csrf_secret)


def test_refresh_token_guardado_cifrado(db, provider):
    _, _, session = _session(db, provider)
    [refresh_token] = provider.refresh_tokens
    assert refresh_token not in session.refresh_token_enc
    assert auth.decrypt_secret(session.refresh_token_enc) == refresh_token


def test_sessao_guarda_retrato_sid_e_id_token(db, provider):
    _, _, session = _session(db, provider, sid="sid-abc")
    assert session.permissions == sorted(set(ANALISTA) - {"ANALISTA"})
    assert session.profiles == ["ANALISTA"]
    assert session.sid == "sid-abc"
    assert session.id_token_hint and session.snapshot_refreshed_at is not None


def test_get_session_valida_e_token_desconhecido(db, provider):
    _, token, session = _session(db, provider)
    assert auth.get_session(db, token) is session
    assert auth.get_session(db, "token-desconhecido") is None


@pytest.mark.parametrize("field", ["expires_at", "absolute_expires_at"])
def test_sessao_expirada(db, provider, field):
    _, token, session = _session(db, provider)
    setattr(session, field, utcnow() - timedelta(seconds=1))
    db.commit()
    assert auth.get_session(db, token) is None


def test_revogar_sessao_apaga_segredos(db, provider):
    _, token, session = _session(db, provider)
    auth.revoke_session(db, session)
    db.commit()
    assert session.revoked_at is not None
    assert session.id_token_hint is None and session.refresh_token_enc is None
    assert auth.get_session(db, token) is None


def test_backchannel_revoga_por_sid_ou_por_subject(db, provider):
    _session(db, provider, sid="s-a")
    _session(db, provider, sid="s-b")
    _session(db, provider, sub="sub-2", sid="s-c")
    assert auth.revoke_sessions_for_logout(db, issuer=ISSUER, sid="s-a", subject=None) == 1
    assert auth.revoke_sessions_for_logout(db, issuer=ISSUER, sid=None, subject="sub-1") == 1
    assert auth.revoke_sessions_for_logout(db, issuer=ISSUER, sid="desconhecido", subject=None) == 0
    db.commit()
    ativas = db.scalars(select(UserSession).where(UserSession.revoked_at.is_(None))).all()
    assert [s.sid for s in ativas] == ["s-c"]


# ── Cifra do refresh token ────────────────────────────────────────────────────

def test_cifra_e_decifra(provider):
    cipher = auth.encrypt_secret("segredo")
    assert cipher != "segredo" and auth.decrypt_secret(cipher) == "segredo"
    assert auth.encrypt_secret(None) is None and auth.decrypt_secret(None) is None


def test_chave_diferente_nao_decifra(provider, monkeypatch):
    cipher = auth.encrypt_secret("segredo")
    monkeypatch.setattr(config, "SESSION_ENCRYPTION_KEY", Fernet.generate_key().decode())
    assert auth.decrypt_secret(cipher) is None


def test_sem_chave_nao_cifra(monkeypatch):
    monkeypatch.setattr(config, "SESSION_ENCRYPTION_KEY", "")
    with pytest.raises(RuntimeError):
        auth.encrypt_secret("segredo")


# ── Registro de login (state, code_verifier, nonce, vínculo com o navegador) ──

BINDING = "navegador-1"


def test_registro_de_login_e_de_uso_unico(db):
    state, verifier, nonce = auth.create_login_request(db, binding=BINDING)
    assert auth.consume_login_request(db, state, binding=BINDING) == (verifier, nonce)
    assert auth.consume_login_request(db, state, binding=BINDING) is None


def test_state_guardado_como_hash(db):
    state, _, _ = auth.create_login_request(db, binding=BINDING)
    row = db.scalar(select(OidcLoginRequest))
    assert row.state_hash == _sha256(state)


def test_state_vazio_ou_desconhecido(db):
    assert auth.consume_login_request(db, None, binding=BINDING) is None
    assert auth.consume_login_request(db, "desconhecido", binding=BINDING) is None


def test_registro_expirado_e_recusado_e_apagado(db):
    state, _, _ = auth.create_login_request(db, binding=BINDING)
    db.scalar(select(OidcLoginRequest)).expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    assert auth.consume_login_request(db, state, binding=BINDING) is None
    assert db.scalar(select(func.count(OidcLoginRequest.id))) == 0


def test_registros_expirados_sao_limpos_ao_criar_outro(db):
    auth.create_login_request(db, binding=BINDING)
    db.scalar(select(OidcLoginRequest)).expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    auth.create_login_request(db, binding=BINDING)
    assert db.scalar(select(func.count(OidcLoginRequest.id))) == 1


# Login CSRF: o state só vale no navegador que iniciou o login.

def test_state_com_outro_navegador_e_recusado_e_consumido(db):
    state, _, _ = auth.create_login_request(db, binding=BINDING)
    assert auth.consume_login_request(db, state, binding="navegador-2") is None
    assert db.scalar(select(func.count(OidcLoginRequest.id))) == 0
    assert auth.consume_login_request(db, state, binding=BINDING) is None


@pytest.mark.parametrize("binding", [None, ""])
def test_state_sem_vinculo_do_navegador_e_recusado(db, binding):
    state, _, _ = auth.create_login_request(db, binding=BINDING)
    assert auth.consume_login_request(db, state, binding=binding) is None
    assert db.scalar(select(func.count(OidcLoginRequest.id))) == 0


def test_vinculo_guardado_somente_como_hash(db):
    auth.create_login_request(db, binding=BINDING)
    row = db.scalar(select(OidcLoginRequest))
    assert row.binding_hash == _sha256(BINDING)
    assert BINDING not in (row.binding_hash, row.state_hash, row.code_verifier, row.nonce)


@pytest.mark.parametrize("binding", ["", None])
def test_registro_de_login_exige_vinculo(db, binding):
    with pytest.raises(ValueError):
        auth.create_login_request(db, binding=binding)
    assert db.scalar(select(func.count(OidcLoginRequest.id))) == 0


# ── Identidade local (issuer + subject) ───────────────────────────────────────

def test_primeiro_login_cria_usuario_e_identidade(db):
    user = _user(db)
    identity = db.scalar(select(OidcIdentity))
    assert (identity.issuer, identity.subject, identity.user_id) == (ISSUER, "sub-1", user.id)
    assert user.email == "pessoa@exemplo.local" and user.username == "pessoa"
    assert user.display_name == "Pessoa Teste" and user.last_profiles == ["ANALISTA"]


def test_login_seguinte_atualiza_os_dados_do_mesmo_registro(db):
    first = _user(db)
    again = auth.upsert_user(db, _claims(email="novo@exemplo.local", name="Nome Novo"), profiles=("GERENTE",))
    db.commit()
    assert again.id == first.id
    assert again.email == "novo@exemplo.local" and again.display_name == "Nome Novo"
    assert again.last_profiles == ["GERENTE"]


def test_mesmo_email_com_outro_subject_vira_outro_usuario(db):
    antigo = _user(db, sub="sub-antigo", email="pessoa@exemplo.local")
    db.add(AssistantConversation(id="c-1", user_id=antigo.id, n8n_session_id="n-1"))
    db.commit()
    novo = _user(db, sub="sub-novo", email="pessoa@exemplo.local")
    assert novo.id != antigo.id
    assert db.scalar(select(func.count(AssistantConversation.id))
                     .where(AssistantConversation.user_id == novo.id)) == 0
    assert db.scalar(select(func.count(OidcIdentity.id))) == 2


def test_usuario_sem_email_usa_o_login_como_nome(db):
    user = auth.upsert_user(db, _claims(email=None, name=None), profiles=())
    db.commit()
    assert user.email == "" and user.display_name == "pessoa" and user.last_profiles == []


# ── Limites de IA ─────────────────────────────────────────────────────────────

def test_limites_pelos_perfis_do_ultimo_login(db):
    assert auth.get_ai_limits(_user(db, profiles=("GERENTE", "ANALISTA"))) == (150, 10)
    assert auth.get_ai_limits(_user(db, sub="sub-2", profiles=())) == (10, 2)


def _uso(db, user, quantidade, *, status="success", ha=timedelta(seconds=5)):
    for i in range(quantidade):
        db.add(AiUsage(user_id=user.id, request_id=f"r-{status}-{i}-{ha.total_seconds()}", status=status,
                       created_at=utcnow() - ha))
    db.commit()


def test_limite_diario_atingido(db):
    user = _user(db, profiles=("CONVIDADO",))
    _uso(db, user, 20, ha=timedelta(seconds=90))  # fora da janela de 1 min, dentro do dia
    rate = auth.check_ai_rate_limit(db, user)
    assert rate["allowed"] is False and rate["reason"] == "daily_limit" and rate["daily_limit"] == 20


def test_limite_por_minuto_atingido(db):
    user = _user(db, profiles=("CONVIDADO",))
    _uso(db, user, 3)
    rate = auth.check_ai_rate_limit(db, user)
    assert rate["allowed"] is False and rate["reason"] == "per_minute_limit"


def test_erros_nao_contam_no_limite(db):
    user = _user(db, profiles=("CONVIDADO",))
    _uso(db, user, 25, status="error")
    assert auth.check_ai_rate_limit(db, user)["allowed"] is True


# ── Auditoria ─────────────────────────────────────────────────────────────────

def test_auditoria_e_evento_de_seguranca(db):
    user = _user(db)
    auth.record_audit(db, user_id=user.id, action="LOGIN_SUCCESS", entity_type="app_user", entity_id=str(user.id))
    auth.record_security_event(db, event_type="ACCESS_DENIED", user_id=user.id, metadata={"path": "/x"})
    db.commit()
    assert db.scalar(select(AuditLog.action)) == "LOGIN_SUCCESS"
    assert db.scalar(select(SecurityEvent.event_type)) == "ACCESS_DENIED"
