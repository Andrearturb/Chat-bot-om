"""
Ponto de entrada da aplicação.
"""

import os

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
from app.api.routes.assistant import router as assistant_router
from app.api.routes.users import router as users_router
from app.api.routes.audit import router as audit_router
from app.core.config import APP_NAME, APP_VERSION, FRONTEND_ORIGINS
from app.db.base import Base
from app.db.session import engine
from app.tasks.tape_scheduler import criar_agendador_tape

from app.models.service import Service          # noqa: F401
from app.models.upload import Upload            # noqa: F401
from app.models.asset_store import AssetStore   # noqa: F401
from app.models.climate_asset import ClimateAsset  # noqa: F401
from app.models.fire_asset import FireAsset     # noqa: F401
from app.models.store_document import StoreDocument  # noqa: F401
from app.models.water_asset import WaterAsset   # noqa: F401
from app.models.auth import (                   # noqa: F401
    Profile, Permission, ProfilePermission,
    AppUser, OidcIdentity, UserSession,
    UserPermissionOverride, AssistantConversation,
    AssistantMessage, AiUsage, AuditLog, SecurityEvent,
)

app = FastAPI(title=APP_NAME, version=APP_VERSION)


def _scheduler_habilitado() -> bool:
    return os.getenv("TAPE_SYNC_SCHEDULE_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}


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


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)

    try:
        from sqlalchemy import text as sa_text
        with engine.connect() as conn:
            conn.execute(sa_text("CREATE EXTENSION IF NOT EXISTS unaccent"))
            conn.commit()
    except Exception:
        pass

    try:
        from app.db.session import SessionLocal
        from app.services.auth import seed_profiles_and_permissions
        with SessionLocal() as db:
            seed_profiles_and_permissions(db)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("seed falhou: %s", exc)

    if _scheduler_habilitado():
        app.state.tape_scheduler = criar_agendador_tape()
        app.state.tape_scheduler.start()


@app.on_event("shutdown")
def on_shutdown() -> None:
    scheduler = getattr(app.state, "tape_scheduler", None)
    if scheduler is not None:
        scheduler.stop()


app.include_router(auth_router)
app.include_router(health_router)
app.include_router(imports_router)
app.include_router(services_router)
app.include_router(chatbot_router)
app.include_router(assets_router)
app.include_router(assistant_router)
app.include_router(users_router)
app.include_router(audit_router)
