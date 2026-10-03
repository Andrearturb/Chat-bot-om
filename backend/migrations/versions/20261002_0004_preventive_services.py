"""Tabela dedicada aos chamados preventivos do app Tape 57532.

Revision ID: 0004
Revises: 0003
"""

from alembic import op
import sqlalchemy as sa


revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "preventive_services" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "preventive_services",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ticket", sa.String(), nullable=False, unique=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("store_name", sa.String(), nullable=True),
        sa.Column("praca", sa.String(), nullable=True),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("subcategory", sa.String(), nullable=True),
        sa.Column("service_description", sa.Text(), nullable=True),
        sa.Column("supplier", sa.String(), nullable=True),
        sa.Column("visit_date", sa.DateTime(), nullable=True),
        sa.Column("solution_text", sa.Text(), nullable=True),
        sa.Column("analyst_responsible", sa.String(), nullable=True),
        sa.Column("non_approval_reason", sa.Text(), nullable=True),
        sa.Column("signature_status", sa.String(), nullable=True),
        sa.Column("signed_pdf_url", sa.Text(), nullable=True),
        sa.Column("created_on", sa.DateTime(), nullable=True),
        sa.Column("completion_date", sa.DateTime(), nullable=True),
        sa.Column("approved_value", sa.Numeric(14, 2), nullable=True),
        sa.Column("periodicity", sa.String(), nullable=True),
        sa.Column("due_date", sa.DateTime(), nullable=True),
        sa.Column("sla_status", sa.String(), nullable=True),
        sa.Column("upload_id", sa.Integer(), sa.ForeignKey("uploads.id"), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("preventive_services")
