"""
Testes de segurança via TestClient.
Usa uma conftest que patcha DATABASE_URL para SQLite antes do import do app.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta

# ── Patcha DATABASE_URL antes de qualquer import do FastAPI ───────────────────
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_api.db")
os.environ.setdefault("INTERNAL_API_KEY", "test-internal-key-xyz")
os.environ.setdefault("API_KEY", "test-api-key-xyz")
os.environ.setdefault("OIDC_ISSUER_URL", "")          # desativa OIDC
os.environ.setdefault("SESSION_SECRET", "test-secret")
os.environ.setdefault("FRONTEND_ORIGINS", "http://localhost:5173")
os.environ.setdefault("BOOTSTRAP_ADMIN_EMAIL", "")
os.environ.setdefault("TAPE_SYNC_SCHEDULE_ENABLED", "false")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

# ── Engine de teste in-memory ─────────────────────────────────────────────────
_test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestSession = sessionmaker(autocommit=False, autoflush=False, bind=_test_engine)

# ── Patch engine ANTES de importar o app ─────────────────────────────────────
import app.db.session as _db_session  # noqa: E402
_db_session.engine = _test_engine
_db_session.SessionLocal = _TestSession

from app.db.base import Base         # noqa: E402
from app.db.session import get_db    # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.models.auth import AppUser, Profile, UserSession  # noqa: E402

# Patch do engine no módulo health (usa engine direto)
import app.api.routes.health as _health  # noqa: E402
_health.engine = _test_engine

# Garante import de todos os modelos para create_all
import app.models.service        # noqa: F401 E402
import app.models.upload         # noqa: F401 E402
import app.models.asset_store    # noqa: F401 E402
import app.models.climate_asset  # noqa: F401 E402
import app.models.fire_asset     # noqa: F401 E402
import app.models.store_document # noqa: F401 E402
import app.models.water_asset    # noqa: F401 E402
import app.models.auth           # noqa: F401 E402

Base.metadata.create_all(bind=_test_engine)

INTERNAL_KEY = os.environ["INTERNAL_API_KEY"]
SESSION_COOKIE = "om_session"


def override_db():
    db = _TestSession()
    try:
        yield db
    finally:
        db.close()


fastapi_app.dependency_overrides[get_db] = override_db


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sha256(v): return hashlib.sha256(v.encode()).hexdigest()


def _seed(db):
    from app.services.auth import seed_profiles_and_permissions
    from sqlalchemy import select
    seed_profiles_and_permissions(db)
    profile = db.scalar(select(Profile).where(Profile.name == "ANALISTA"))
    user = AppUser(email="api@test.com", display_name="API Test",
                   profile_id=profile.id, status="active")
    db.add(user); db.flush()
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    now = datetime.utcnow()
    db.add(UserSession(
        user_id=user.id, session_token_hash=_sha256(token), csrf_secret=csrf,
        created_at=now, last_seen_at=now,
        expires_at=now + timedelta(hours=1), absolute_expires_at=now + timedelta(hours=8),
    ))
    db.commit()
    return token, csrf


@pytest.fixture(autouse=True)
def clean():
    Base.metadata.drop_all(bind=_test_engine)
    Base.metadata.create_all(bind=_test_engine)
    yield
    Base.metadata.drop_all(bind=_test_engine)


@pytest.fixture
def client():
    with TestClient(fastapi_app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def authed():
    db = _TestSession()
    token, csrf = _seed(db); db.close()
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

    def test_callback_define_cookie_na_resposta_302(self, client, monkeypatch):
        """O callback deve plantar o cookie na própria resposta de redirect."""
        from sqlalchemy import select
        import app.api.routes.auth as auth_routes
        from app.services.auth import seed_profiles_and_permissions

        db = _TestSession()
        seed_profiles_and_permissions(db)
        profile = db.scalar(select(Profile).where(Profile.name == "ADMINISTRADOR"))
        user = AppUser(
            email="callback@test.com",
            display_name="Callback Test",
            profile_id=profile.id,
            status="active",
        )
        db.add(user); db.commit(); db.refresh(user)

        monkeypatch.setattr(auth_routes, "exchange_code", lambda code, verifier: {"access_token": "test-token"})
        monkeypatch.setattr(auth_routes, "get_userinfo", lambda token: {"sub": "callback-sub"})
        monkeypatch.setattr(auth_routes, "resolve_or_create_user", lambda session, userinfo: session.get(AppUser, user.id))
        auth_routes._pending_states["state-cookie-test"] = {"verifier": "verifier"}

        r = client.get(
            "/auth/callback?code=abc&state=state-cookie-test",
            follow_redirects=False,
        )
        db.close()

        assert r.status_code == 302
        assert r.headers["location"] == "http://localhost:5173"
        cookie = r.headers.get("set-cookie", "")
        assert "om_session=" in cookie
        assert "HttpOnly" in cookie
        assert "Path=/" in cookie
        assert "SameSite=lax" in cookie


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
