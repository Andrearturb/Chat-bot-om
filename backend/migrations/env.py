"""
Ambiente do Alembic.

Usa o engine do próprio aplicativo (DATABASE_URL). Quando o aplicativo sobe, ele passa a
conexão pronta em ``config.attributes["connection"]``; pela linha de comando
(``alembic upgrade head``) o engine é criado aqui.
"""

from alembic import context

import app.models.registry  # noqa: F401  (registra todos os modelos)
from app.db.base import Base

config = context.config
target_metadata = Base.metadata


def _configure(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        render_as_batch=True,   # ALTER portátil: o Postgres usa ALTER normal e o SQLite dos testes recria a tabela
    )


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _configure(connection)
        with context.begin_transaction():
            context.run_migrations()
        return

    from app.db.session import engine

    with engine.connect() as connection:
        _configure(connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError("Use as migrações com conexão (modo online).")
run_migrations_online()
