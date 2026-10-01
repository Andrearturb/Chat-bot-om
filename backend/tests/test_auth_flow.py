"""Fluxo OIDC completo no backend, com o Keycloak simulado (tests/oidc_fake.py)."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.dates import utcnow
from tests.api_harness import TestSession, fastapi_app, reset_database  # antes de qualquer import de app.*
from app.core import config  # isort: skip
from app.models.auth import AppUser, OidcLoginRequest, SecurityEvent, UserSession  # isort: skip
from tests.oidc_fake import ADMINISTRADOR, ANALISTA, CLIENT_ID, ISSUER, authorization_params

FRONTEND = "http://localhost:5173"
CONVIDADO = ["CONVIDADO", "assistant.use", "assistant.history", "indicators.view", "assets.view"]
BINDING_COOKIE = "om_login_binding"


@pytest.fixture(autouse=True)
def clean():
    reset_database()
    yield
    reset_database()


@pytest.fixture
def client(provider):
    with TestClient(fastapi_app, raise_server_exceptions=False) as c:
        yield c


def _start(client, path: str = "/auth/login") -> dict:
    r = client.get(path, follow_redirects=False)
    assert r.status_code == 302
    return authorization_params(r.headers["location"])


def _login(client, provider, *, sub: str = "u1", roles=ANALISTA, sid: str | None = None):
    params = _start(client)
    code = provider.issue_code(sub, roles, nonce=params["nonce"], code_challenge=params["code_challenge"], sid=sid)
    r = client.get(f"/auth/callback?code={code}&state={params['state']}", follow_redirects=False)
    return r, params, code


def _count(model, *where) -> int:
    query = select(func.count()).select_from(model)
    if where:
        query = query.where(*where)
    with TestSession() as db:
        return db.scalar(query)


def _age_snapshots() -> None:
    with TestSession() as db:
        for session in db.scalars(select(UserSession)):
            session.snapshot_refreshed_at = utcnow() - timedelta(minutes=6)
        db.commit()


def _csrf(client) -> str:
    return client.get("/auth/me").json()["csrf_token"]


def _set_cookie(response, name: str) -> str | None:
    """Linha Set-Cookie completa do cookie ``name`` (ou None)."""
    for line in response.headers.get_list("set-cookie"):
        if line.startswith(name + "="):
            return line
    return None


# ── Início do login ───────────────────────────────────────────────────────────

def test_login_redireciona_com_pkce_nonce_e_state(client):
    params = _start(client)
    assert params["code_challenge_method"] == "S256" and params["code_challenge"]
    assert params["nonce"] and params["state"] and "prompt" not in params
    assert _count(OidcLoginRequest) == 1


def test_cadastro_abre_o_keycloak_com_prompt_create(client):
    assert _start(client, "/auth/register")["prompt"] == "create"


def test_login_com_keycloak_fora_do_ar_volta_ao_login(client, provider):
    provider.offline = True
    r = client.get("/auth/login", follow_redirects=False)
    assert r.headers["location"] == f"{FRONTEND}/login?auth_error=provider_unavailable"


# ── Callback ──────────────────────────────────────────────────────────────────

def test_callback_cria_sessao_com_cookie_seguro_e_sem_tokens_no_navegador(client, provider):
    r, _, _ = _login(client, provider)
    assert r.status_code == 302 and r.headers["location"] == FRONTEND
    assert r.headers["cache-control"] == "no-store"
    cookie = r.headers["set-cookie"]
    assert "om_session=" in cookie and "HttpOnly" in cookie and "Path=/" in cookie and "SameSite=lax" in cookie

    me_response = client.get("/auth/me")
    assert me_response.headers["cache-control"] == "no-store"
    me = me_response.json()
    assert set(me) == {"id", "email", "username", "display_name", "profile", "profile_display", "profiles",
                       "permissions", "csrf_token", "ai_usage"}
    assert me["profile"] == "ANALISTA" and me["profile_display"] == "Analista"
    assert me["profiles"] == ["ANALISTA"] and "assets.create" in me["permissions"]


def test_replay_do_callback_nao_cria_segunda_sessao(client, provider):
    _, params, code = _login(client, provider)
    r = client.get(f"/auth/callback?code={code}&state={params['state']}", follow_redirects=False)
    assert r.headers["location"] == f"{FRONTEND}/login?auth_error=invalid_state"
    assert _count(UserSession) == 1


def test_state_desconhecido_e_recusado(client):
    r = client.get("/auth/callback?code=x&state=nao-existe", follow_redirects=False)
    assert r.headers["location"] == f"{FRONTEND}/login?auth_error=invalid_state"
    assert _count(UserSession) == 0


def test_erro_do_provedor_consome_o_state(client, provider):
    params = _start(client)
    r = client.get(f"/auth/callback?error=access_denied&state={params['state']}", follow_redirects=False)
    assert r.headers["location"] == f"{FRONTEND}/login?auth_error=provider_error"
    code = provider.issue_code("u1", ANALISTA, nonce=params["nonce"], code_challenge=params["code_challenge"])
    r = client.get(f"/auth/callback?code={code}&state={params['state']}", follow_redirects=False)
    assert r.headers["location"] == f"{FRONTEND}/login?auth_error=invalid_state"


def test_nonce_divergente_nao_cria_sessao(client, provider):
    params = _start(client)
    code = provider.issue_code("u1", ANALISTA, nonce="outro", code_challenge=params["code_challenge"])
    r = client.get(f"/auth/callback?code={code}&state={params['state']}", follow_redirects=False)
    assert r.headers["location"] == f"{FRONTEND}/login?auth_error=token_exchange"
    assert _count(UserSession) == 0


def test_conta_sem_perfil_nao_cria_sessao_e_encerra_o_sso(client, provider):
    r, _, _ = _login(client, provider, roles=[])
    location = r.headers["location"]
    assert location.startswith(ISSUER + "/protocol/openid-connect/logout?")
    params = authorization_params(location)
    assert params["post_logout_redirect_uri"] == f"{FRONTEND}/login?auth_error=not_released"
    assert params["client_id"] == CLIENT_ID and params["id_token_hint"]
    assert "set-cookie" not in r.headers
    assert _count(UserSession) == 0 and _count(AppUser) == 1
    assert len(provider.revoked) == 1


def test_keycloak_fora_do_ar_no_callback(client, provider):
    params = _start(client)
    code = provider.issue_code("u1", ANALISTA, nonce=params["nonce"], code_challenge=params["code_challenge"])
    provider.offline = True
    r = client.get(f"/auth/callback?code={code}&state={params['state']}", follow_redirects=False)
    assert r.headers["location"] == f"{FRONTEND}/login?auth_error=provider_unavailable"


# ── Login CSRF: o state só vale no navegador que iniciou o login ──────────────

def test_login_redirect_define_cookie_de_vinculo_httponly_lax_no_path_auth(client):
    r = client.get("/auth/login", follow_redirects=False)
    cookie = _set_cookie(r, BINDING_COOKIE)
    assert cookie is not None, r.headers.get_list("set-cookie")
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Path=/auth" in cookie
    assert f"Max-Age={config.OIDC_LOGIN_REQUEST_TTL_SECONDS}" in cookie
    assert "Secure" not in cookie  # SESSION_COOKIE_SECURE desligado nos testes
    value = cookie.split(";", 1)[0].split("=", 1)[1]
    assert len(value) >= 32  # secrets.token_urlsafe(32)


def test_cadastro_tambem_define_o_cookie_de_vinculo(client):
    r = client.get("/auth/register", follow_redirects=False)
    assert _set_cookie(r, BINDING_COOKIE) is not None


def test_segundo_login_do_mesmo_navegador_reutiliza_o_cookie_de_vinculo(client):
    first = client.get("/auth/login", follow_redirects=False)
    second = client.get("/auth/login", follow_redirects=False)
    register = client.get("/auth/register", follow_redirects=False)
    values = {_set_cookie(r, BINDING_COOKIE).split(";", 1)[0] for r in (first, second, register)}
    assert len(values) == 1
    assert _count(OidcLoginRequest) == 3


def test_abas_paralelas_do_mesmo_navegador_completam_o_login(client, provider):
    tab_a, tab_b = _start(client), _start(client)
    assert tab_a["state"] != tab_b["state"]
    for params, sub in ((tab_a, "u1"), (tab_b, "u1")):
        code = provider.issue_code(sub, ANALISTA, nonce=params["nonce"], code_challenge=params["code_challenge"])
        r = client.get(f"/auth/callback?code={code}&state={params['state']}", follow_redirects=False)
        assert r.headers["location"] == FRONTEND
        assert _set_cookie(r, BINDING_COOKIE) is None  # o callback não apaga o vínculo
    assert _count(UserSession) == 2


def test_login_csrf_callback_em_outro_navegador_e_recusado(client, provider):
    params = _start(client)  # navegador A (a vítima) iniciou o login e tem o cookie de vínculo
    code = provider.issue_code("atacante", ANALISTA, nonce=params["nonce"],
                               code_challenge=params["code_challenge"])
    callback = f"/auth/callback?code={code}&state={params['state']}"

    with TestClient(fastapi_app, raise_server_exceptions=False) as other:  # navegador B, sem o cookie
        r = other.get(callback, follow_redirects=False)
    assert r.headers["location"] == f"{FRONTEND}/login?auth_error=invalid_state"
    assert _set_cookie(r, "om_session") is None
    assert _count(UserSession) == 0 and _count(AppUser) == 0
    assert provider.token_requests == 0  # o código nem chegou ao Keycloak

    # O state foi consumido pela tentativa: o navegador A também não consegue mais usá-lo.
    r = client.get(callback, follow_redirects=False)
    assert r.headers["location"] == f"{FRONTEND}/login?auth_error=invalid_state"
    assert _count(UserSession) == 0
    assert client.get("/auth/me").status_code == 401


def test_login_csrf_cookie_de_vinculo_diferente_e_recusado(client, provider):
    params = _start(client)
    code = provider.issue_code("atacante", ANALISTA, nonce=params["nonce"],
                               code_challenge=params["code_challenge"])
    with TestClient(fastapi_app, raise_server_exceptions=False) as other:
        other.get("/auth/login", follow_redirects=False)  # B tem o próprio vínculo, mas outro valor
        r = other.get(f"/auth/callback?code={code}&state={params['state']}", follow_redirects=False)
    assert r.headers["location"] == f"{FRONTEND}/login?auth_error=invalid_state"
    assert _count(UserSession) == 0 and provider.token_requests == 0


# ── Renovação pelo uso da API ─────────────────────────────────────────────────

def test_troca_de_perfil_no_keycloak_vale_na_renovacao(client, provider):
    _login(client, provider)
    provider.roles_by_sub["u1"] = CONVIDADO
    _age_snapshots()
    assert client.get("/auth/me").json()["profile"] == "CONVIDADO"
    assert client.get("/assets/stores").status_code == 200
    assert client.get("/health").status_code == 403  # settings.view: Analista tinha, Convidado não


def test_acesso_retirado_no_keycloak_derruba_a_sessao(client, provider):
    _login(client, provider)
    provider.roles_by_sub["u1"] = []
    _age_snapshots()
    assert client.get("/auth/me").status_code == 401


# ── Logout ────────────────────────────────────────────────────────────────────

def test_logout_revoga_sessao_e_refresh_token(client, provider):
    _login(client, provider)
    r = client.post("/auth/logout", headers={"X-CSRF-Token": _csrf(client)})
    assert r.status_code == 200 and "Max-Age=0" in r.headers["set-cookie"]
    assert r.headers["cache-control"] == "no-store"
    url = r.json()["logout_url"]
    assert url.startswith(ISSUER + "/protocol/openid-connect/logout?")
    params = authorization_params(url)
    assert params["post_logout_redirect_uri"] == f"{FRONTEND}/login" and params["id_token_hint"]
    assert len(provider.revoked) == 1
    assert _count(UserSession, UserSession.revoked_at.is_(None)) == 0


# ── Backchannel logout ────────────────────────────────────────────────────────

def _backchannel(client, token: str):
    cookies = dict(client.cookies)
    client.cookies.clear()  # chamada servidor a servidor: sem cookie nem CSRF
    try:
        return client.post("/auth/backchannel-logout", data={"logout_token": token})
    finally:
        for name, value in cookies.items():
            client.cookies.set(name, value)


def test_backchannel_com_sid_derruba_a_sessao_na_hora(client, provider):
    _login(client, provider, sid="sid-x")
    r = _backchannel(client, provider.sign(provider.logout_claims(sid="sid-x")))
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    assert client.get("/auth/me").status_code == 401


def test_backchannel_so_com_sub_derruba_todas_as_sessoes(client, provider):
    _login(client, provider, sid="sid-a")
    _login(client, provider, sid="sid-b")
    assert _backchannel(client, provider.sign(provider.logout_claims(sub="u1"))).status_code == 200
    assert _count(UserSession, UserSession.revoked_at.is_(None)) == 0


def test_backchannel_de_sessao_desconhecida_responde_200_sem_efeito(client, provider):
    _login(client, provider, sid="sid-x")
    assert _backchannel(client, provider.sign(provider.logout_claims(sid="sid-outra"))).status_code == 200
    assert client.get("/auth/me").status_code == 200
    assert _count(SecurityEvent, SecurityEvent.event_type == "BACKCHANNEL_LOGOUT_REJECTED") == 0


def test_logout_token_invalido_e_recusado(client, provider):
    _login(client, provider, sid="sid-x")
    for token in ("invalido", "", provider.sign(provider.logout_claims(sid="sid-x", nonce="n"))):
        assert _backchannel(client, token).status_code == 400
    assert client.get("/auth/me").status_code == 200
    assert _count(SecurityEvent, SecurityEvent.event_type == "BACKCHANNEL_LOGOUT_REJECTED") == 3


# ── Subida do backend ─────────────────────────────────────────────────────────

def test_backend_nao_sobe_sem_chave_de_sessao_valida(provider, monkeypatch):
    monkeypatch.setattr(config, "SESSION_ENCRYPTION_KEY", "invalida")
    with pytest.raises(RuntimeError, match="SESSION_ENCRYPTION_KEY"):
        with TestClient(fastapi_app):
            pass


def test_startup_verifica_a_chave_antes_de_tocar_no_banco(provider, monkeypatch):
    import app.main as main

    calls: list[str] = []

    def chave_recusada() -> None:
        calls.append("check")
        raise RuntimeError("sentinela")

    def migrar(engine) -> str:
        calls.append("migrations")
        return "migrado"

    monkeypatch.setattr(main, "_check_session_encryption_key", chave_recusada)
    monkeypatch.setattr(main, "run_migrations", migrar)
    with pytest.raises(RuntimeError, match="sentinela"):
        with TestClient(fastapi_app):
            pass
    assert calls == ["check"]


@pytest.mark.parametrize("chave", ["", "invalida"])
def test_verificacao_da_chave_recusa_ausente_ou_invalida(provider, monkeypatch, chave):
    import app.main as main

    monkeypatch.setattr(config, "SESSION_ENCRYPTION_KEY", chave)
    with pytest.raises(RuntimeError, match="SESSION_ENCRYPTION_KEY"):
        main._check_session_encryption_key()


def test_verificacao_da_chave_aceita_chave_valida_e_ignora_sem_oidc(provider, monkeypatch):
    import app.main as main

    main._check_session_encryption_key()  # a chave do provedor simulado é uma chave Fernet válida
    monkeypatch.setattr(config, "OIDC_ISSUER_URL", "")
    monkeypatch.setattr(config, "SESSION_ENCRYPTION_KEY", "")
    main._check_session_encryption_key()  # sem OIDC o backend não guarda refresh token


def test_rota_de_usuarios_nao_existe_mais(client, provider):
    _login(client, provider)
    assert client.get("/users").status_code == 404
