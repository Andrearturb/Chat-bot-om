"""Adoção de bancos anteriores à coluna de contexto de ativos."""

from sqlalchemy import create_engine, inspect

from app.db.base import Base
from app.db.migrations import run_migrations
import app.models.registry  # noqa: F401


def test_adopta_banco_legado_e_migra_ate_o_head():
    """Banco anterior ao Alembic é adotado e migrado até o head. A coluna de
    contexto de ativos é criada pela 0002 e removida pela 0008, então no head ela
    não existe: o estado conversacional passou a viver no dataTable do n8n."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    assert run_migrations(engine) == "adotado"
    columns = {item["name"] for item in inspect(engine).get_columns("assistant_conversations")}
    assert "asset_query_state" not in columns


def test_adocao_remove_a_coluna_de_contexto_de_banco_pre_0008():
    """Um banco que ainda carrega asset_query_state é detectado pelo marcador,
    stampado na revisão que o esquema comprova e levado ao head, onde a 0008
    remove a coluna. Entrada diferente, mesmo destino."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "ALTER TABLE assistant_conversations ADD COLUMN asset_query_state JSON"
        )

    assert run_migrations(engine) == "adotado"
    columns = {item["name"] for item in inspect(engine).get_columns("assistant_conversations")}
    assert "asset_query_state" not in columns


def test_adota_esquema_que_ja_possui_a_coluna():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    assert run_migrations(engine) == "adotado"
    assert run_migrations(engine) == "migrado"


def test_adota_estado_de_ativos_e_aplica_campos_pendentes_da_corretiva():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        for column in ("sla_late", "approved_value", "raw_status"):
            connection.exec_driver_sql(f"ALTER TABLE services DROP COLUMN {column}")

    assert run_migrations(engine) == "adotado"
    columns = {item["name"] for item in inspect(engine).get_columns("services")}
    assert {"sla_late", "approved_value", "raw_status"} <= columns
