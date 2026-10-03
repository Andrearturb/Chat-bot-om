"""Estado estruturado da última consulta de ativos da conversa.

Revision ID: 0002
Revises: 0001
"""

from alembic import op
import sqlalchemy as sa


revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("assistant_conversations", sa.Column("asset_query_state", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("assistant_conversations", "asset_query_state")
