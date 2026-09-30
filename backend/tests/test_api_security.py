"""
Testes de segurança via TestClient (harness em tests/api_harness.py).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.api_harness import INTERNAL_KEY, SESSION_COOKIE, fastapi_app, reset_database, seed_session
from tests.oidc_fake import ANALISTA

ANALISTA_PERMISSIONS = [role for role in ANALISTA if role != "ANALISTA"]


@pytest.fixture(autouse=True)
def clean():
    reset_database()
    yield
    reset_database()


@pytest.fixture
def client():
    with TestClient(fastapi_app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def authed():
    token, csrf = seed_session(ANALISTA_PERMISSIONS)
    with TestClient(fastapi_app, raise_server_exceptions=False) as c:
        c.cookies.set(SESSION_COOKIE, token)
        c._csrf = csrf
        yield c


# ── Health ─────────────────────────────────────────────────────────────────────

class TestHealth:
    def test_live_publico(self, client):
        r = client.get("/health/live")
        assert r.status_code == 200 and r.json()["status"] == "ok"

    def test_health_sem_sessao_401(self, client):
        assert client.get("/health").status_code == 401


# ── Auth endpoints ─────────────────────────────────────────────────────────────

class TestAuthEndpoints:
    def test_me_sem_sessao_401(self, client):
        assert client.get("/auth/me").status_code == 401

    def test_me_com_sessao_200(self, authed):
        r = authed.get("/auth/me")
        assert r.status_code == 200
        d = r.json()
        assert "email" in d and "permissions" in d and "csrf_token" in d


# ── CSRF ───────────────────────────────────────────────────────────────────────

class TestCSRF:
    def test_post_sem_csrf_403(self, authed):
        assert authed.post("/auth/logout").status_code == 403

    def test_post_csrf_errado_403(self, authed):
        assert authed.post("/auth/logout", headers={"X-CSRF-Token": "errado"}).status_code == 403

    def test_get_sem_csrf_ok(self, authed):
        assert authed.get("/auth/me").status_code == 200

    def test_post_csrf_correto_200(self, authed):
        r = authed.post("/auth/logout", headers={"X-CSRF-Token": authed._csrf})
        assert r.status_code == 200


# ── Rotas protegidas ───────────────────────────────────────────────────────────

class TestProtectedRoutes:
    def test_services_sem_sessao_401(self, client):
        assert client.get("/services").status_code == 401

    def test_services_com_sessao_200(self, authed):
        assert authed.get("/services").status_code == 200

    def test_assets_sem_sessao_401(self, client):
        assert client.get("/assets/stores").status_code == 401

    def test_assets_com_sessao_200(self, authed):
        assert authed.get("/assets/stores").status_code == 200


# ── Internal API Key ───────────────────────────────────────────────────────────

class TestInternalKey:
    def test_sem_chave_401(self, client):
        r = client.post("/chatbot/structured-query", json={"query_shape": "count", "state": {}})
        assert r.status_code == 401

    def test_chave_errada_401(self, client):
        r = client.post("/chatbot/structured-query",
                        json={"query_shape": "count", "state": {}},
                        headers={"X-Internal-API-Key": "errada"})
        assert r.status_code == 401

    def test_chave_correta_nao_401(self, client):
        r = client.post("/chatbot/structured-query",
                        json={"query_shape": "count", "state": {}},
                        headers={"X-Internal-API-Key": INTERNAL_KEY})
        assert r.status_code != 401


# ── Permissões granulares ──────────────────────────────────────────────────────

class TestPermissions:
    def test_analista_nao_deleta_asset(self, authed):
        r = authed.delete("/assets/climatization/999", headers={"X-CSRF-Token": authed._csrf})
        assert r.status_code in (403, 404)

    def test_audit_sem_permissao_403(self, authed):
        assert authed.get("/audit/logs").status_code == 403

    def test_users_sem_permissao_403(self, authed):
        assert authed.get("/users").status_code == 403


# ── Assistant ─────────────────────────────────────────────────────────────────

class TestAssistant:
    def test_chat_sem_sessao_401(self, client):
        assert client.post("/assistant/chat", json={"message": "oi"}).status_code == 401

    def test_conversations_sem_sessao_401(self, client):
        assert client.get("/assistant/conversations").status_code == 401

    def test_conversa_inexistente_404(self, authed):
        assert authed.get("/assistant/conversations/inexistente-xyz").status_code == 404
