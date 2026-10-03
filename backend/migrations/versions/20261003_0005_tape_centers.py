"""dCentros e referência técnica da loja nos chamados.

Revision ID: 0005
Revises: 0004
"""

from alembic import op
import sqlalchemy as sa


revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def _create_index_if_missing(table: str, name: str, columns: list[str]) -> None:
    names = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes(table)}
    if name not in names:
        op.create_index(name, table, columns)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "tape_centers" not in inspector.get_table_names():
        op.create_table(
            "tape_centers",
            sa.Column("record_id", sa.BigInteger(), primary_key=True),
            sa.Column("unique_number", sa.Integer(), nullable=True),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("name", sa.String(255), nullable=True),
            sa.Column("short_name", sa.String(255), nullable=True),
            sa.Column("bcps_number", sa.String(100), nullable=True),
            sa.Column("sap_number", sa.String(100), nullable=True),
            sa.Column("cost_center", sa.String(100), nullable=True),
            sa.Column("praca", sa.String(255), nullable=True),
            sa.Column("status", sa.String(100), nullable=True),
            sa.Column("brand", sa.String(100), nullable=True),
            sa.Column("business_type", sa.String(100), nullable=True),
            sa.Column("company", sa.String(100), nullable=True),
            sa.Column("uf", sa.String(2), nullable=True),
            sa.Column("cnpj", sa.String(30), nullable=True),
            sa.Column("address", sa.Text(), nullable=True),
            sa.Column("record_url", sa.Text(), nullable=True),
            sa.Column("upload_id", sa.Integer(), sa.ForeignKey("uploads.id"), nullable=False),
            sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        )

    for name in ("unique_number", "name", "bcps_number"):
        _create_index_if_missing("tape_centers", f"ix_tape_centers_{name}", [name])

    for table in ("services", "preventive_services"):
        columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns(table)}
        if "tape_center_record_id" not in columns:
            op.add_column(table, sa.Column("tape_center_record_id", sa.BigInteger(), nullable=True))
        _create_index_if_missing(table, f"ix_{table}_tape_center_record_id", ["tape_center_record_id"])


def downgrade() -> None:
    for table in ("services", "preventive_services"):
        op.drop_index(f"ix_{table}_tape_center_record_id", table_name=table)
        op.drop_column(table, "tape_center_record_id")
    for name in ("unique_number", "name", "bcps_number"):
        op.drop_index(f"ix_tape_centers_{name}", table_name="tape_centers")
    op.drop_table("tape_centers")
