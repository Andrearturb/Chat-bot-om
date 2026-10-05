"""
Migrações do banco (Alembic) na subida do aplicativo.

- Banco novo ou já gerenciado pelo Alembic: aplica as migrações pendentes.
- Banco criado antes do Alembic (tabelas existem, sem ``alembic_version``): é adotado
  na revisão correspondente ao esquema existente e recebe migrações posteriores.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

BACKEND_DIR = Path(__file__).resolve().parents[2]
BASELINE_REVISION = "0001"
ASSET_QUERY_REVISION = "0002"
CORRECTIVE_REVISION = "0003"
COSTS_REVISION = "0007"
STATE_MOVED_REVISION = "0008"


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
            conversation_columns = {
                column["name"] for column in inspect(connection).get_columns("assistant_conversations")
            }
            service_columns = {
                column["name"] for column in inspect(connection).get_columns("services")
            }
            has_asset_state = "asset_query_state" in conversation_columns
            has_corrective_fields = {"sla_late", "approved_value", "raw_status"} <= service_columns
            # A 0007 cria maintenance_costs e a 0008 remove asset_query_state, então
            # "tabela presente e coluna ausente" é a assinatura do head. Sem este
            # marcador, dropar a coluna na 0008 tirou o degrau mais alto da escada:
            # todo esquema atual caía em BASELINE e a adoção reaplicava desde a
            # 0001, inclusive a 0006, que é irreversível e apaga linhas.
            has_costs = "maintenance_costs" in tables

            # Stampar a revisão mais alta que o esquema detectado comprova e então
            # SEMPRE rodar upgrade até head — nunca pular para "head" direto. Uma
            # migração futura sem marcador próprio nesta lista continua sendo
            # aplicada, porque o upgrade (idempotente) corre de qualquer forma.
            #
            # Cada degrau exige TODOS os marcadores dos degraus abaixo: um esquema
            # com maintenance_costs mas sem os campos da corretiva não está no
            # head, e stampá-lo lá impediria a 0003 de devolver esses campos.
            revision = (
                STATE_MOVED_REVISION if has_costs and has_corrective_fields and not has_asset_state else
                COSTS_REVISION if has_costs and has_corrective_fields and has_asset_state else
                CORRECTIVE_REVISION if has_asset_state and has_corrective_fields else
                ASSET_QUERY_REVISION if has_asset_state else BASELINE_REVISION
            )
            command.stamp(config, revision)
            command.upgrade(config, "head")
            return "adotado"
        command.upgrade(config, "head")
        return "migrado"
