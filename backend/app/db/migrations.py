"""
Migrações do banco (Alembic) na subida do aplicativo.

- Banco novo ou já gerenciado pelo Alembic: aplica as migrações pendentes.
- Banco criado antes do Alembic (tabelas existem, sem ``alembic_version``): é adotado, ou
  seja, marcado como estando na migração inicial, sem recriar nada.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

BACKEND_DIR = Path(__file__).resolve().parents[2]
BASELINE_REVISION = "0001"


def _alembic_config() -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    return config


def run_migrations(engine: Engine) -> str:
    """Leva o banco à última migração. Devolve ``"adotado"`` ou ``"migrado"``."""
    config = _alembic_config()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        tables = set(inspect(connection).get_table_names())
        if "alembic_version" not in tables and "app_users" in tables:
            command.stamp(config, BASELINE_REVISION)
            return "adotado"
        command.upgrade(config, "head")
        return "migrado"
