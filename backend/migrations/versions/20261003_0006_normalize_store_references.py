"""Loja única no dCentros para chamados e inventário.

Revision ID: 0006
Revises: 0005
"""

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {item["name"] for item in sa.inspect(op.get_bind()).get_columns(table)}


def _has_fk(table: str, column: str) -> bool:
    return any(column in item["constrained_columns"] for item in sa.inspect(op.get_bind()).get_foreign_keys(table))


def _index_names(table: str) -> set[str]:
    return {item["name"] for item in sa.inspect(op.get_bind()).get_indexes(table)}


def _backfill_asset_stores() -> None:
    conn = op.get_bind()
    centers = conn.execute(sa.text(
        "SELECT record_id, bcps_number, sap_number FROM tape_centers"
    )).mappings().all()
    by_bcps = {item["bcps_number"]: item["record_id"] for item in centers if item["bcps_number"]}
    by_sap = {item["sap_number"]: item["record_id"] for item in centers if item["sap_number"]}
    stores = conn.execute(sa.text(
        "SELECT id, bpcs_number, sap_number, tape_center_record_id FROM asset_stores"
    )).mappings().all()
    used: dict[int, int] = {}
    unmatched: list[int] = []
    for store in stores:
        center_id = store["tape_center_record_id"] or by_bcps.get(store["bpcs_number"]) or by_sap.get(store["sap_number"])
        if center_id is None:
            unmatched.append(store["id"])
            continue
        if center_id in used and used[center_id] != store["id"]:
            raise RuntimeError(
                f"Lojas de ativos {used[center_id]} e {store['id']} apontam ao mesmo dCentros {center_id}; "
                "consolide os vínculos antes da migração."
            )
        used[center_id] = store["id"]
        conn.execute(sa.text(
            "UPDATE asset_stores SET tape_center_record_id=:center_id WHERE id=:store_id"
        ), {"center_id": center_id, "store_id": store["id"]})

    for store_id in unmatched:
        for table in ("climate_assets", "fire_assets", "water_assets", "store_documents", "audit_logs"):
            count = conn.execute(sa.text(
                f"SELECT count(*) FROM {table} WHERE store_id=:store_id"
            ), {"store_id": store_id}).scalar_one()
            if count:
                raise RuntimeError(
                    f"Loja de ativos {store_id} não existe no dCentros e possui vínculos em {table}; "
                    "corrija o cadastro antes da migração."
                )
        conn.execute(sa.text("DELETE FROM asset_stores WHERE id=:store_id"), {"store_id": store_id})


def _seed_asset_stores() -> None:
    conn = op.get_bind()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    conn.execute(sa.text(
        "INSERT INTO asset_stores (tape_center_record_id, created_at, updated_at) "
        "SELECT c.record_id, :now, :now FROM tape_centers c "
        "WHERE NOT EXISTS (SELECT 1 FROM asset_stores a WHERE a.tape_center_record_id=c.record_id)"
    ), {"now": now})


def upgrade() -> None:
    asset_columns = _columns("asset_stores")
    if "tape_center_record_id" not in asset_columns:
        op.add_column("asset_stores", sa.Column("tape_center_record_id", sa.BigInteger(), nullable=True))
        asset_columns.add("tape_center_record_id")

    if "store_name" in asset_columns:
        _backfill_asset_stores()
        for name in ("ix_asset_stores_store_key", "ix_asset_stores_store_name", "ix_asset_stores_praca"):
            if name in _index_names("asset_stores"):
                op.drop_index(name, table_name="asset_stores")
        with op.batch_alter_table("asset_stores") as batch:
            constraints = {item["name"] for item in sa.inspect(op.get_bind()).get_unique_constraints("asset_stores")}
            if "uq_asset_stores_store_key" in constraints:
                batch.drop_constraint("uq_asset_stores_store_key", type_="unique")
            for name in ("store_key", "store_name", "bpcs_number", "sap_number", "praca"):
                batch.drop_column(name)

    if not _has_fk("asset_stores", "tape_center_record_id"):
        with op.batch_alter_table("asset_stores") as batch:
            batch.create_foreign_key(
                "fk_asset_stores_tape_center", "tape_centers",
                ["tape_center_record_id"], ["record_id"],
            )
    constraints = {item["name"] for item in sa.inspect(op.get_bind()).get_unique_constraints("asset_stores")}
    if "uq_asset_stores_tape_center_record_id" not in constraints:
        with op.batch_alter_table("asset_stores") as batch:
            batch.create_unique_constraint("uq_asset_stores_tape_center_record_id", ["tape_center_record_id"])
    if "ix_asset_stores_tape_center_record_id" not in _index_names("asset_stores"):
        op.create_index("ix_asset_stores_tape_center_record_id", "asset_stores", ["tape_center_record_id"])

    for table, obsolete in (
        ("services", ("store_name", "bpcs_number", "sap_number")),
        ("preventive_services", ("store_name",)),
    ):
        old = [column for column in obsolete if column in _columns(table)]
        needs_fk = not _has_fk(table, "tape_center_record_id")
        if old or needs_fk:
            with op.batch_alter_table(table) as batch:
                for column in old:
                    batch.drop_column(column)
                if needs_fk:
                    batch.create_foreign_key(
                        f"fk_{table}_tape_center", "tape_centers",
                        ["tape_center_record_id"], ["record_id"],
                    )

    _seed_asset_stores()


def downgrade() -> None:
    raise RuntimeError("A reversão exige restaurar os campos legados a partir do dCentros.")
