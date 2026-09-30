"""
Ajustes incrementais de schema.

O projeto cria as tabelas com ``Base.metadata.create_all``, que não adiciona
colunas novas em tabelas já existentes. Este módulo aplica, de forma
idempotente, somente as colunas adicionadas depois da criação inicial.
"""

from __future__ import annotations

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

# (tabela, coluna, DDL do tipo) — apenas colunas anuláveis, sem default.
_ADDED_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("app_users", "username", "VARCHAR(150)"),
    ("user_sessions", "id_token_hint", "TEXT"),
)


def apply_schema_updates(engine: Engine) -> list[str]:
    """Adiciona as colunas ausentes. Retorna a lista de colunas criadas."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    created: list[str] = []

    with engine.begin() as connection:
        for table, column, ddl in _ADDED_COLUMNS:
            if table not in existing_tables:
                continue
            columns = {col["name"] for col in inspector.get_columns(table)}
            if column in columns:
                continue
            connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
            created.append(f"{table}.{column}")

    if created:
        logger.info("Schema atualizado: %s", ", ".join(created))
    return created
