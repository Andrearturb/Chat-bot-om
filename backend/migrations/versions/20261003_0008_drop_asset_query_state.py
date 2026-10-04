"""Remove assistant_conversations.asset_query_state.

O estado conversacional passa a viver só no dataTable do n8n.

Revision ID: 0008
Revises: 0007
"""

from alembic import op
import sqlalchemy as sa


revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    colunas = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("assistant_conversations")}
    if "asset_query_state" in colunas:
        op.drop_column("assistant_conversations", "asset_query_state")


def downgrade() -> None:
    colunas = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("assistant_conversations")}
    if "asset_query_state" not in colunas:
        op.add_column("assistant_conversations", sa.Column("asset_query_state", sa.JSON(), nullable=True))
