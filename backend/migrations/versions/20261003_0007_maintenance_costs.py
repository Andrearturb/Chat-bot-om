"""Partidas de custos FBL3N.

Revision ID: 0007
Revises: 0006
"""

from alembic import op
import sqlalchemy as sa


revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    upload_columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("uploads")}
    if "source_type" not in upload_columns:
        op.add_column("uploads", sa.Column("source_type", sa.String(30), nullable=True))
    upload_indexes = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes("uploads")}
    if "ix_uploads_source_type" not in upload_indexes:
        op.create_index("ix_uploads_source_type", "uploads", ["source_type"])
    if "maintenance_costs" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            "maintenance_costs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("upload_id", sa.Integer(), sa.ForeignKey("uploads.id"), nullable=False),
            sa.Column("conta_razao", sa.String(30), nullable=False),
            sa.Column("posting_date", sa.Date(), nullable=False),
            sa.Column("document_date", sa.Date(), nullable=True),
            sa.Column("document_number", sa.String(100), nullable=True),
            sa.Column("posting_key", sa.String(20), nullable=True),
            sa.Column("document_type", sa.String(20), nullable=True),
            sa.Column("amount", sa.Numeric(14, 2), nullable=False),
            sa.Column("division", sa.String(100), nullable=True),
            sa.Column("cost_center", sa.String(100), nullable=False),
            sa.Column("tape_center_record_id", sa.BigInteger(), sa.ForeignKey("tape_centers.record_id"), nullable=True),
            sa.Column("attribution_source", sa.String(30), nullable=True),
            sa.Column("supplier_name", sa.String(255), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        )
    names = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes("maintenance_costs")}
    for name, columns in (
        ("ix_maintenance_costs_conta_razao", ["conta_razao"]),
        ("ix_maintenance_costs_cost_center", ["cost_center"]),
        ("ix_maintenance_costs_tape_center_record_id", ["tape_center_record_id"]),
        ("ix_maintenance_costs_account_posting", ["conta_razao", "posting_date"]),
    ):
        if name not in names:
            op.create_index(name, "maintenance_costs", columns)


def downgrade() -> None:
    op.drop_table("maintenance_costs")
    op.drop_index("ix_uploads_source_type", table_name="uploads")
    op.drop_column("uploads", "source_type")
