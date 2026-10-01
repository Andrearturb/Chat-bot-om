"""
Harness do TestClient: SQLite em memória no lugar do PostgreSQL.

Importe este módulo antes de qualquer import de ``app.main``: ele define o
ambiente de teste e troca o engine do banco. O OIDC fica desligado por padrão;
os testes de fluxo instalam o Keycloak simulado com a fixture ``provider``.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_api.db")
os.environ.setdefault("INTERNAL_API_KEY", "test-internal-key-xyz")
os.environ.setdefault("API_KEY", "test-api-key-xyz")
os.environ["OIDC_ISSUER_URL"] = ""
os.environ.setdefault("SESSION_SECRET", "test-secret")
os.environ.setdefault("FRONTEND_ORIGINS", "http://localhost:5173")
os.environ["OIDC_POST_LOGOUT_REDIRECT_URI"] = "http://localhost:5173/login"
os.environ["SESSION_COOKIE_SECURE"] = "false"
os.environ["KEYCLOAK_CONSOLE_URL"] = ""
# Sem exceção: o agendador da Tape faria chamadas reais se o .env (carregado por app.core.config)
# o deixasse ligado, e brigaria com o SQLite compartilhado dos testes.
os.environ["TAPE_SYNC_SCHEDULE_ENABLED"] = "false"

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

import app.db.session as _db_session  # noqa: E402

_db_session.engine = test_engine
_db_session.SessionLocal = TestSession

import app.api.routes.health as _health  # noqa: E402
import app.models.asset_store  # noqa: F401,E402
import app.models.auth  # noqa: F401,E402
import app.models.climate_asset  # noqa: F401,E402
import app.models.fire_asset  # noqa: F401,E402
import app.models.service  # noqa: F401,E402
import app.models.store_document  # noqa: F401,E402
import app.models.upload  # noqa: F401,E402
import app.models.water_asset  # noqa: F401,E402
from app.core.dates import utcnow
from app.core import config  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.models.auth import AppUser, UserSession  # noqa: E402

_health.engine = test_engine
# Independe do .env local: OIDC desligado até um teste instalar o provedor simulado.
config.OIDC_ISSUER_URL = ""

SESSION_COOKIE = "om_session"
INTERNAL_KEY = os.environ["INTERNAL_API_KEY"]


def _override_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


fastapi_app.dependency_overrides[get_db] = _override_db


def reset_database() -> None:
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)


def seed_session(permissions, profiles=("ANALISTA",), email: str = "api@test.com") -> tuple[str, str]:
    """Usuário + sessão com retrato em dia (não consulta o Keycloak). Retorna (token, csrf)."""
    db = TestSession()
    try:
        user = AppUser(email=email, display_name="API Test", last_profiles=list(profiles))
        db.add(user)
        db.flush()
        token, csrf, now = secrets.token_urlsafe(32), secrets.token_urlsafe(32), utcnow()
        db.add(UserSession(
            user_id=user.id, session_token_hash=hashlib.sha256(token.encode()).hexdigest(),
            csrf_secret=csrf, created_at=now, last_seen_at=now,
            expires_at=now + timedelta(hours=1), absolute_expires_at=now + timedelta(hours=8),
            permissions=sorted(permissions), profiles=list(profiles), snapshot_refreshed_at=now,
        ))
        db.commit()
        return token, csrf
    finally:
        db.close()
