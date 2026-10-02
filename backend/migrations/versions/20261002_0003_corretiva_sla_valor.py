"""Campos de SLA, valor aprovado e status cru para o painel de corretiva.

Revision ID: 0003
Revises: 0002
"""

from alembic import op
import sqlalchemy as sa


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Em testes que criam o esquema via Base.metadata.create_all() (modelo Python
    # já com estas colunas) e depois "adotam" o banco replaying as migrações desde
    # o baseline, a tabela já tem estas colunas quando esta migração roda — checar
    # antes evita "duplicate column" nesse caminho, sem mudar o mecanismo de adoção.
    bind = op.get_bind()
    existentes = {coluna["name"] for coluna in sa.inspect(bind).get_columns("services")}

    if "sla_late" not in existentes:
        op.add_column("services", sa.Column("sla_late", sa.String(), nullable=True))
    if "approved_value" not in existentes:
        op.add_column("services", sa.Column("approved_value", sa.Numeric(14, 2), nullable=True))
    if "raw_status" not in existentes:
        op.add_column("services", sa.Column("raw_status", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("services", "raw_status")
    op.drop_column("services", "approved_value")
    op.drop_column("services", "sla_late")
