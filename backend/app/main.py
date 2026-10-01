"""
Ponto de entrada da aplicação.
"""

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.api.routes.auth import router as auth_router
from app.api.routes.health import router as health_router
from app.api.routes.imports import router as imports_router
from app.api.routes.services import router as services_router
from app.api.routes.chatbot import router as chatbot_router
from app.api.routes.assets import router as assets_router
from app.api.routes.assets_export import router as assets_export_router
from app.api.routes.assistant import router as assistant_router
from app.api.routes.audit import router as audit_router
from app.core import config
from app.core.config import APP_NAME, APP_VERSION, FRONTEND_ORIGINS
from app.db.migrations import run_migrations
from app.db.session import engine
from app.tasks.tape_scheduler import criar_agendador_tape

import app.models.registry  # noqa: F401  (registra todos os modelos em Base.metadata)


def _scheduler_habilitado() -> bool:
    return os.getenv("TAPE_SYNC_SCHEDULE_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}


def _check_session_encryption_key() -> None:
    """Sem chave válida o backend não consegue guardar o refresh token: falha na subida."""
    if not config.OIDC_ISSUER_URL:
        return
    from cryptography.fernet import Fernet
    try:
        Fernet(config.SESSION_ENCRYPTION_KEY.encode())
    except (ValueError, TypeError) as exc:
        raise RuntimeError(
            "SESSION_ENCRYPTION_KEY ausente ou inválida. Gere com: python -c "
            "\"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        ) from exc


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Subida e parada: verifica a chave de sessão, prepara o banco e liga o agendador da Tape."""
    _check_session_encryption_key()

    run_migrations(engine)

    try:
        from sqlalchemy import text as sa_text
        with engine.connect() as conn:
            conn.execute(sa_text("CREATE EXTENSION IF NOT EXISTS unaccent"))
            conn.commit()
    except Exception:
        pass

    if _scheduler_habilitado():
        app.state.tape_scheduler = criar_agendador_tape()
        app.state.tape_scheduler.start()

    try:
        yield
    finally:
        scheduler = getattr(app.state, "tape_scheduler", None)
        if scheduler is not None:
            scheduler.stop()


app = FastAPI(title=APP_NAME, version=APP_VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token", "X-Internal-API-Key", "X-Api-Key"],
)

app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next) -> Response:
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; frame-ancestors 'none'; "
        "script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; connect-src 'self'"
    )
    if os.getenv("APP_ENV", "development") == "production":
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response


app.include_router(auth_router)
app.include_router(health_router)
app.include_router(imports_router)
app.include_router(services_router)
app.include_router(chatbot_router)
app.include_router(assets_router)
app.include_router(assets_export_router)
app.include_router(assistant_router)
app.include_router(audit_router)
