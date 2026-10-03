"""
Migrações do banco (Alembic).

- Banco novo: as migrações criam o esquema completo.
- Banco antigo (criado por ``create_all`` antes do Alembic): é adotado sem recriar tabelas
  nem perder dados.
- Os modelos e as migrações não podem divergir: quem mudar um modelo precisa criar a
  migração correspondente, senão o teste de divergência falha.
"""

from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory

import app.models.registry  # noqa: F401  (registra todos os modelos em Base.metadata)
from app.core.dates import utcnow
from app.db.base import Base
from app.db.migrations import _alembic_config, run_migrations


def head_atual() -> str:
    return ScriptDirectory.from_config(_alembic_config()).get_current_head()


def motor(tmp_path, nome="banco.db"):
    return create_engine(f"sqlite:///{tmp_path / nome}")


def versao(engine) -> str | None:
    with engine.connect() as conn:
        if "alembic_version" not in inspect(conn).get_table_names():
            return None
        return conn.execute(text("select version_num from alembic_version")).scalar()


def test_banco_novo_recebe_o_esquema_completo(tmp_path):
    engine = motor(tmp_path)
    assert run_migrations(engine) == "migrado"
    tabelas = set(inspect(engine).get_table_names())
    assert set(Base.metadata.tables) <= tabelas
    assert "alembic_version" in tabelas
    assert versao(engine) is not None


def test_rodar_de_novo_nao_faz_nada(tmp_path):
    engine = motor(tmp_path)
    run_migrations(engine)
    primeira = versao(engine)
    assert run_migrations(engine) == "migrado"
    assert versao(engine) == primeira


def test_banco_criado_antes_do_alembic_e_adotado_sem_perder_dados(tmp_path):
    engine = motor(tmp_path)
    Base.metadata.create_all(engine)   # como o app criava o banco antes
    with engine.begin() as conn:
        conn.execute(text("insert into app_users (email, display_name, created_at, updated_at) "
                          "values ('ana@gentil.test', 'Ana', :agora, :agora)"), {"agora": utcnow().isoformat(sep=" ")})
    assert versao(engine) is None

    assert run_migrations(engine) == "adotado"

    assert versao(engine) == head_atual()
    with engine.connect() as conn:
        assert conn.execute(text("select email from app_users")).scalar() == "ana@gentil.test"
    assert run_migrations(engine) == "migrado"   # a partir daí é um banco comum do Alembic


def test_banco_totalmente_adotado_ainda_assim_roda_upgrade_para_o_head(tmp_path, monkeypatch):
    """Mesmo quando o banco legado já bate com todos os marcadores conhecidos,
    o upgrade até head precisa rodar de qualquer forma — senão uma migração
    futura, sem marcador próprio no "has_..." atual, nunca seria aplicada a um
    banco que a adoção já classificou como "tem tudo"."""
    import app.db.migrations as migrations_module

    engine = motor(tmp_path)
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("insert into app_users (email, display_name, created_at, updated_at) "
                          "values ('ana@gentil.test', 'Ana', :agora, :agora)"), {"agora": utcnow().isoformat(sep=" ")})

    chamadas_upgrade = []
    original_upgrade = migrations_module.command.upgrade

    def espiao(config, revision):
        chamadas_upgrade.append(revision)
        return original_upgrade(config, revision)

    monkeypatch.setattr(migrations_module.command, "upgrade", espiao)

    assert run_migrations(engine) == "adotado"
    assert "head" in chamadas_upgrade


def test_migracoes_e_modelos_estao_em_dia(tmp_path):
    engine = motor(tmp_path)
    run_migrations(engine)
    with engine.connect() as conn:
        diferencas = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diferencas == [], f"Modelo alterado sem migração: {diferencas}"


def test_banco_vazio_nunca_e_confundido_com_banco_antigo(tmp_path):
    engine = motor(tmp_path)
    assert versao(engine) is None and not inspect(engine).get_table_names()
    assert run_migrations(engine) == "migrado"
    assert "app_users" in inspect(engine).get_table_names()
