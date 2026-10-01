"""Renovação do retrato de acesso da sessão (app/services/session_refresh.py)."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import sessionmaker

from app.models.auth import AppUser, SecurityEvent, UserSession
from app.services import auth, oidc, session_refresh
from app.services.permissions import snapshot_from_roles
from app.services.session_refresh import REFRESH_RETRY_SECONDS, SessionRevoked, ensure_fresh_snapshot
from tests.oidc_fake import ANALISTA, login_tokens

CONVIDADO = ["CONVIDADO", "assistant.use", "assistant.history", "indicators.view", "assets.view"]


def _login(db, provider, sub: str = "u1", roles=ANALISTA) -> UserSession:
    tokens = login_tokens(provider, sub, roles)
    snapshot = snapshot_from_roles(roles)
    user = auth.upsert_user(db, tokens.access_claims, profiles=snapshot.profiles)
    token = auth.create_session(db, user, tokens=tokens, snapshot=snapshot)
    db.commit()
    return auth.get_session(db, token)


def _age(db, session: UserSession, minutes: int = 6) -> None:
    session.snapshot_refreshed_at = datetime.utcnow() - timedelta(minutes=minutes)
    db.commit()


def _events(db, event_type: str) -> list[SecurityEvent]:
    return db.scalars(select(SecurityEvent).where(SecurityEvent.event_type == event_type)).all()


def test_retrato_recente_nao_chama_o_keycloak(db, provider):
    session = _login(db, provider)
    before = provider.token_requests
    assert ensure_fresh_snapshot(db, session) is session
    assert provider.token_requests == before


def test_retrato_vencido_renova_e_aplica_a_troca_de_perfil(db, provider):
    session = _login(db, provider)
    old_refresh = session.refresh_token_enc
    provider.roles_by_sub["u1"] = CONVIDADO
    _age(db, session)
    result = ensure_fresh_snapshot(db, session)
    assert result.profiles == ["CONVIDADO"]
    assert "assets.create" not in result.permissions and "assets.view" in result.permissions
    assert result.refresh_token_enc != old_refresh
    assert result.snapshot_refreshed_at > datetime.utcnow() - timedelta(minutes=1)
    assert db.get(AppUser, result.user_id).last_profiles == ["CONVIDADO"]


def test_provedor_sem_novo_refresh_token_preserva_o_atual_ate_a_revogacao(db, provider, monkeypatch):
    session = _login(db, provider)
    original = auth.decrypt_secret(session.refresh_token_enc)
    refresh = oidc.refresh

    def sem_rotacao(token, *, expected_sub):
        renewed = refresh(token, expected_sub=expected_sub)
        provider.refresh_tokens[token] = provider.refresh_tokens.pop(renewed.refresh_token)
        return replace(renewed, refresh_token=None)

    monkeypatch.setattr(oidc, "refresh", sem_rotacao)
    _age(db, session)
    renewed_session = ensure_fresh_snapshot(db, session)
    assert auth.decrypt_secret(renewed_session.refresh_token_enc) == original

    provider.roles_by_sub["u1"] = []
    _age(db, session)
    with pytest.raises(SessionRevoked, match="access_removed"):
        ensure_fresh_snapshot(db, session)
    assert provider.revoked == [original]


def test_renovacao_recusada_revoga_a_sessao(db, provider):
    session = _login(db, provider)
    provider.disabled_subs.add("u1")
    _age(db, session)
    with pytest.raises(SessionRevoked) as exc:
        ensure_fresh_snapshot(db, session)
    assert exc.value.reason == "invalid_grant"
    assert session.revoked_at is not None and session.refresh_token_enc is None
    assert len(_events(db, "SESSION_REVOKED")) == 1


def test_erro_de_configuracao_do_client_mantem_sessao_na_carencia(db, provider, monkeypatch):
    session = _login(db, provider)
    _age(db, session)
    monkeypatch.setattr(provider, "_token", lambda _: httpx.Response(401, json={"error": "invalid_client"}))
    result = ensure_fresh_snapshot(db, session)
    assert result.id == session.id
    assert result.revoked_at is None
    assert result.refresh_failed_since is not None


def test_sem_permissao_no_keycloak_revoga_e_devolve_o_refresh_token(db, provider):
    session = _login(db, provider)
    provider.roles_by_sub["u1"] = []
    _age(db, session)
    with pytest.raises(SessionRevoked) as exc:
        ensure_fresh_snapshot(db, session)
    assert exc.value.reason == "access_removed"
    assert len(provider.revoked) == 1
    assert len(_events(db, "ACCESS_REMOVED")) == 1


def test_duas_abas_usam_o_refresh_token_uma_unica_vez(db, provider):
    session = _login(db, provider)
    _age(db, session)
    outra_conexao = sessionmaker(bind=db.get_bind(), autoflush=False)()
    aba_b = outra_conexao.get(UserSession, session.id)  # carregada antes da renovação da aba A
    before = provider.token_requests

    ensure_fresh_snapshot(db, session)                  # aba A renova
    result = ensure_fresh_snapshot(outra_conexao, aba_b)  # aba B ainda tem o retrato velho em memória

    assert provider.token_requests == before + 1
    assert result.revoked_at is None
    assert result.snapshot_refreshed_at > datetime.utcnow() - timedelta(minutes=1)
    outra_conexao.close()


def test_keycloak_fora_do_ar_mantem_o_retrato_e_limita_as_tentativas(db, provider):
    session = _login(db, provider)
    _age(db, session)
    provider.offline = True
    attempts = provider.attempts

    result = ensure_fresh_snapshot(db, session)
    assert result.revoked_at is None and result.refresh_failed_since is not None
    assert "assets.create" in result.permissions
    assert provider.attempts == attempts + 1

    for _ in range(3):
        ensure_fresh_snapshot(db, session)
    assert provider.attempts == attempts + 1  # no máximo 1 tentativa a cada 30 s

    session.refresh_attempted_at -= timedelta(seconds=REFRESH_RETRY_SECONDS + 1)
    db.commit()
    ensure_fresh_snapshot(db, session)
    assert provider.attempts == attempts + 2


def test_keycloak_fora_do_ar_por_15_minutos_encerra_a_sessao(db, provider):
    session = _login(db, provider)
    _age(db, session)
    provider.offline = True
    ensure_fresh_snapshot(db, session)
    session.refresh_failed_since = datetime.utcnow() - timedelta(minutes=15, seconds=1)
    db.commit()
    with pytest.raises(SessionRevoked) as exc:
        ensure_fresh_snapshot(db, session)
    assert exc.value.reason == "provider_unavailable"
    assert session.revoked_at is not None


def test_keycloak_de_volta_limpa_a_falha(db, provider):
    session = _login(db, provider)
    _age(db, session)
    provider.offline = True
    ensure_fresh_snapshot(db, session)
    provider.offline = False
    session.refresh_attempted_at -= timedelta(seconds=REFRESH_RETRY_SECONDS + 1)
    db.commit()
    result = ensure_fresh_snapshot(db, session)
    assert result.refresh_failed_since is None and result.refresh_attempted_at is None


def test_sessao_revogada_por_outra_requisicao_nao_renova(db, provider):
    session = _login(db, provider)
    _age(db, session)
    outra_conexao = sessionmaker(bind=db.get_bind(), autoflush=False)()
    auth.revoke_session(outra_conexao, outra_conexao.get(UserSession, session.id))
    outra_conexao.commit()
    outra_conexao.close()
    before = provider.token_requests
    with pytest.raises(SessionRevoked) as exc:
        ensure_fresh_snapshot(db, session)
    assert exc.value.reason == "revoked"
    assert provider.token_requests == before


# ─── Carência de 15 min e trava por sessão ────────────────────────────────────

def _outra_conexao(db):
    return sessionmaker(bind=db.get_bind(), autoflush=False)()


def test_falha_na_tentativa_apos_a_carencia_de_15_minutos_encerra_a_sessao(db, provider):
    session = _login(db, provider)
    _age(db, session)
    agora = datetime.utcnow()
    session.refresh_failed_since = agora - timedelta(minutes=15, seconds=1)
    session.refresh_attempted_at = agora - timedelta(seconds=REFRESH_RETRY_SECONDS + 1)  # já pode tentar de novo
    db.commit()
    provider.offline = True
    attempts = provider.attempts

    with pytest.raises(SessionRevoked) as exc:
        ensure_fresh_snapshot(db, session)

    assert exc.value.reason == "provider_unavailable"
    assert provider.attempts == attempts + 1  # tentou uma vez; a falha esgotou a carência
    assert session.revoked_at is not None and session.refresh_token_enc is None
    assert len(_events(db, "SESSION_REVOKED")) == 1


def test_outra_aba_ja_falhou_e_a_aba_com_retrato_velho_nao_tenta_de_novo(db, provider):
    session = _login(db, provider)
    _age(db, session)
    outra_conexao = _outra_conexao(db)
    aba_b = outra_conexao.get(UserSession, session.id)  # carregada antes da falha da aba A
    provider.offline = True
    attempts = provider.attempts

    ensure_fresh_snapshot(db, session)  # aba A tenta, falha e registra a tentativa
    assert provider.attempts == attempts + 1
    result = ensure_fresh_snapshot(outra_conexao, aba_b)  # aba B relê a linha travada e vê a tentativa recente

    assert provider.attempts == attempts + 1
    assert result.revoked_at is None and result.refresh_failed_since is not None
    outra_conexao.close()


def test_outra_aba_ja_falhou_e_a_carencia_acabou_a_aba_com_retrato_velho_encerra_sem_tentar(db, provider):
    session = _login(db, provider)
    _age(db, session)
    outra_conexao = _outra_conexao(db)
    aba_b = outra_conexao.get(UserSession, session.id)
    provider.offline = True
    attempts = provider.attempts
    ensure_fresh_snapshot(db, session)
    session.refresh_failed_since = datetime.utcnow() - timedelta(minutes=15, seconds=1)
    db.commit()

    with pytest.raises(SessionRevoked) as exc:
        ensure_fresh_snapshot(outra_conexao, aba_b)

    assert exc.value.reason == "provider_unavailable"
    assert provider.attempts == attempts + 1  # só a tentativa da aba A
    outra_conexao.close()


def test_acesso_removido_encerra_a_transacao_antes_de_revogar_no_keycloak(db, provider, monkeypatch):
    session = _login(db, provider)
    provider.roles_by_sub["u1"] = []
    _age(db, session)
    visto = {}
    original = oidc.revoke_refresh_token

    def espiao(refresh_token):
        visto["em_transacao"] = db.in_transaction()  # a trava da linha já foi liberada?
        return original(refresh_token)

    monkeypatch.setattr(oidc, "revoke_refresh_token", espiao)

    with pytest.raises(SessionRevoked) as exc:
        ensure_fresh_snapshot(db, session)

    assert exc.value.reason == "access_removed"
    assert visto == {"em_transacao": False}
    assert len(provider.revoked) == 1
    assert session.revoked_at is not None
    assert len(_events(db, "ACCESS_REMOVED")) == 1


def test_sessao_travada_por_outra_requisicao_nao_espera_e_nao_chama_o_keycloak(db, provider, monkeypatch):
    session = _login(db, provider)
    _age(db, session)
    antes = (list(session.permissions), list(session.profiles), session.snapshot_refreshed_at,
             session.refresh_token_enc)
    monkeypatch.setattr(session_refresh, "_lock_session", lambda db, session_id: None)  # SKIP LOCKED: outra requisição renova
    attempts = provider.attempts

    result = ensure_fresh_snapshot(db, session)

    assert not db.in_transaction()  # não segura conexão nem trava enquanto a outra requisição renova
    assert provider.attempts == attempts
    assert result.id == session.id and result.revoked_at is None
    assert (list(result.permissions), list(result.profiles), result.snapshot_refreshed_at,
            result.refresh_token_enc) == antes


def test_sessao_travada_e_revogada_por_outra_requisicao_levanta_revoked(db, provider, monkeypatch):
    session = _login(db, provider)
    _age(db, session)
    outra_conexao = _outra_conexao(db)
    auth.revoke_session(outra_conexao, outra_conexao.get(UserSession, session.id))
    outra_conexao.commit()
    outra_conexao.close()
    monkeypatch.setattr(session_refresh, "_lock_session", lambda db, session_id: None)
    attempts = provider.attempts

    with pytest.raises(SessionRevoked) as exc:
        ensure_fresh_snapshot(db, session)

    assert exc.value.reason == "revoked"
    assert provider.attempts == attempts
    assert not db.in_transaction()


def test_sessao_travada_e_apagada_levanta_revoked(db, provider, monkeypatch):
    session = _login(db, provider)
    _age(db, session)
    outra_conexao = _outra_conexao(db)
    outra_conexao.delete(outra_conexao.get(UserSession, session.id))
    outra_conexao.commit()
    outra_conexao.close()
    monkeypatch.setattr(session_refresh, "_lock_session", lambda db, session_id: None)
    attempts = provider.attempts

    with pytest.raises(SessionRevoked) as exc:
        ensure_fresh_snapshot(db, session)

    assert exc.value.reason == "revoked"
    assert provider.attempts == attempts
    assert not db.in_transaction()


# ─── touch_session não espera a requisição que está renovando ─────────────────

def _envelhecer_last_seen(db, session: UserSession, segundos: int = 120):
    session.last_seen_at = datetime.utcnow() - timedelta(seconds=segundos)
    db.commit()
    return session.last_seen_at, session.expires_at


def test_touch_normal_atualiza_last_seen_e_a_expiracao_ociosa(db, provider):
    session = _login(db, provider)
    last_seen, expires = _envelhecer_last_seen(db, session)

    auth.touch_session(db, session)

    assert session.last_seen_at > last_seen
    assert session.expires_at > expires
    assert session.last_seen_at > datetime.utcnow() - timedelta(minutes=1)


def test_touch_dentro_de_um_minuto_nao_escreve(db, provider, monkeypatch):
    session = _login(db, provider)
    last_seen, expires = _envelhecer_last_seen(db, session, segundos=30)
    monkeypatch.setattr(auth, "_lock_for_touch", lambda db, session_id: pytest.fail("não devia travar a linha"))

    auth.touch_session(db, session)

    assert (session.last_seen_at, session.expires_at) == (last_seen, expires)


def test_touch_com_a_linha_travada_por_outra_requisicao_pula_sem_esperar(db, provider, monkeypatch):
    session = _login(db, provider)
    last_seen, expires = _envelhecer_last_seen(db, session)
    monkeypatch.setattr(auth, "_lock_for_touch", lambda db, session_id: None)  # SKIP LOCKED: outra requisição renova

    auth.touch_session(db, session)  # não levanta

    assert not db.in_transaction()  # encerrou a transação: não segura conexão esperando a outra requisição
    assert (session.last_seen_at, session.expires_at) == (last_seen, expires)


def test_as_travas_da_linha_da_sessao_usam_skip_locked_no_postgresql():
    """Sem SKIP LOCKED (o SQLite ignora FOR UPDATE), as requisições esperariam a renovação do Keycloak."""
    renovacao = session_refresh._lock_statement(1)
    toque = auth._touch_lock_statement(1)
    for nome, stmt in (("renovação", renovacao), ("touch", toque)):
        sql = str(stmt.compile(dialect=postgresql.dialect()))
        assert "FOR UPDATE SKIP LOCKED" in sql, nome
    assert renovacao.get_execution_options().get("populate_existing") is True
