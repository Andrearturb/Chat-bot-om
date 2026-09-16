"""
Ponto de entrada da aplicação.

Este módulo cria a instância principal do FastAPI, registra as rotas
e garante a criação das tabelas no banco de dados.
"""

import os

from dotenv import load_dotenv

# Carrega o .env antes de qualquer import que leia variáveis de ambiente
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.api.routes.health import router as health_router
from app.api.routes.imports import router as imports_router
from app.api.routes.services import router as services_router
from app.api.routes.chatbot import router as chatbot_router
from app.core.config import APP_NAME, APP_VERSION
from app.db.base import Base
from app.db.session import engine
from app.tasks.tape_scheduler import criar_agendador_tape

# Importa os models para que o SQLAlchemy reconheça as tabelas antes do create_all
from app.models.service import Service  # noqa: F401
from app.models.upload import Upload    # noqa: F401

# Instância principal da aplicação
app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
)


def _scheduler_habilitado() -> bool:
    valor = os.getenv("TAPE_SYNC_SCHEDULE_ENABLED", "true").strip().lower()
    return valor in {"1", "true", "yes", "on"}


# Libera acesso do front local ao backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://frontend:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Comprime respostas grandes
app.add_middleware(
    GZipMiddleware,
    minimum_size=1000,
)


@app.on_event("startup")
def on_startup() -> None:
    """
    Cria as tabelas no banco de dados ao iniciar a aplicação.

    O create_all cria todas as tabelas definidas nos modelos registrados
    no Base.metadata. Como os modelos são importados acima, todas as
    colunas atuais são incluídas na criação.
    """
    Base.metadata.create_all(bind=engine)

    if _scheduler_habilitado():
        app.state.tape_scheduler = criar_agendador_tape()
        app.state.tape_scheduler.start()


@app.on_event("shutdown")
def on_shutdown() -> None:
    """Encerra o agendador da Tape quando a aplicação finaliza."""
    scheduler = getattr(app.state, "tape_scheduler", None)

    if scheduler is not None:
        scheduler.stop()


# Registro das rotas da aplicação
app.include_router(health_router)
app.include_router(imports_router)
app.include_router(services_router)
app.include_router(chatbot_router)
