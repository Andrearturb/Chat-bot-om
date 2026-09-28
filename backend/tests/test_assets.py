from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models.asset_store import AssetStore
from app.models.climate_asset import ClimateAsset
from app.models.fire_asset import FireAsset
from app.models.service import Service
from app.models.store_document import StoreDocument
from app.models.upload import Upload
from app.models.water_asset import WaterAsset
from app.schemas.assets import ClimateAssetCreate, FireAssetCreate, WaterAssetCreate
from app.services import assets as assets_service
from app.services.assets import (
    create_asset,
    document_response,
    get_store_detail,
    list_stores,
    sync_asset_stores,
)


@pytest.fixture
def asset_db() -> Session:
    engine = create_engine("sqlite:///:memory:")
    for model in (AssetStore, ClimateAsset, FireAsset, WaterAsset, StoreDocument):
        model
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    upload = Upload(source_file_name="asset-test", total_rows=3)
    session.add(upload)
    session.flush()
    session.add_all([
        Service(ticket="A-1", status="Em Aberto", store_name="Loja Centro", bpcs_number="B1", sap_number="S1", praca="Natal", upload_id=upload.id),
        Service(ticket="A-2", status="Concluído", store_name="Loja Centro", bpcs_number="B1", sap_number="S1", praca="Natal", upload_id=upload.id),
        Service(ticket="A-3", status="Em atendimento", store_name="Loja Norte", bpcs_number="B2", sap_number=None, praca="Mossoró", upload_id=upload.id),
    ])
    session.commit()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


def test_sync_asset_stores_deduplicates_services(asset_db):
    sync_asset_stores(asset_db)
    sync_asset_stores(asset_db)
    stores = asset_db.scalars(select(AssetStore).order_by(AssetStore.store_name)).all()
    assert len(stores) == 2
    assert stores[0].store_key == "sap:s1"
    assert stores[1].store_key == "bpcs:b2"


def test_list_stores_search_and_counts(asset_db):
    stores = list_stores(asset_db, q="b1")
    assert len(stores) == 1
    assert stores[0]["store_name"] == "Loja Centro"
    assert stores[0]["climatization_count"] == 0


def test_equipment_crud_and_stable_codes(asset_db):
    store = list_stores(asset_db)[0]
    climate = create_asset(asset_db, store["id"], ClimateAsset, ClimateAssetCreate(equipment_type="Cassete", capacity_btu=36000, location="Salão"), "CLI")
    fire = create_asset(asset_db, store["id"], FireAsset, FireAssetCreate(location="Entrada", extinguisher_agent="ABC"), "INC")
    water = create_asset(asset_db, store["id"], WaterAsset, WaterAssetCreate(location="Copa"), "AGU")
    detail = get_store_detail(asset_db, store["id"])
    assert climate.asset_code.startswith("CLI-s1-")
    assert fire.asset_code.startswith("INC-s1-")
    assert water.asset_code.startswith("AGU-s1-")
    assert len(detail["climatization"]) == 1
    assert len(detail["fire_safety"]) == 1
    assert len(detail["water"]) == 1


def test_document_status_is_calculated(asset_db, monkeypatch, tmp_path):
    monkeypatch.setattr(assets_service, "ASSET_DOCUMENTS_DIR", str(tmp_path))
    store = list_stores(asset_db)[0]
    document = StoreDocument(
        store_id=store["id"], document_type="AVCB", original_filename="avcb.pdf",
        stored_filename="stored.pdf", mime_type="application/pdf", file_size=4,
        expiration_date=date.today() + timedelta(days=20),
    )
    asset_db.add(document)
    asset_db.commit()
    assert document_response(document)["status"] == "Próximo do vencimento"


def test_document_file_storage_uses_uuid_and_persistent_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(assets_service, "ASSET_DOCUMENTS_DIR", str(tmp_path))
    from fastapi import UploadFile
    from io import BytesIO
    import asyncio

    upload = UploadFile(filename="manual.pdf", file=BytesIO(b"pdf"), headers={"content-type": "application/pdf"})
    stored, mime, size = asyncio.run(assets_service.save_document_file(upload))
    assert stored.endswith(".pdf")
    assert stored != "manual.pdf"
    assert mime == "application/pdf"
    assert size == 3
    assert (tmp_path / stored).read_bytes() == b"pdf"


def test_document_file_type_and_size_are_validated(tmp_path, monkeypatch):
    monkeypatch.setattr(assets_service, "ASSET_DOCUMENTS_DIR", str(tmp_path))
    from fastapi import UploadFile
    from io import BytesIO
    import asyncio

    invalid = UploadFile(filename="manual.exe", file=BytesIO(b"x"), headers={"content-type": "application/octet-stream"})
    with pytest.raises(ValueError):
        asyncio.run(assets_service.save_document_file(invalid))


def test_asset_code_does_not_reuse_sequence_after_delete(asset_db):
    from app.services.assets import delete_asset

    store = next(item for item in list_stores(asset_db) if item["sap_number"] == "S1")
    first = create_asset(
        asset_db,
        store["id"],
        ClimateAsset,
        ClimateAssetCreate(equipment_type="Cassete", capacity_btu=36000, location="Salão"),
        "CLI",
    )
    second = create_asset(
        asset_db,
        store["id"],
        ClimateAsset,
        ClimateAssetCreate(equipment_type="Cassete", capacity_btu=12000, location="Estoque"),
        "CLI",
    )
    delete_asset(asset_db, ClimateAsset, first.id)
    third = create_asset(
        asset_db,
        store["id"],
        ClimateAsset,
        ClimateAssetCreate(equipment_type="Cassete", capacity_btu=24000, location="Copa"),
        "CLI",
    )

    assert second.asset_code.endswith("-002")
    assert third.asset_code.endswith("-003")


def test_sync_promotes_bpcs_to_sap_and_merges_legacy_duplicates(asset_db):
    sync_asset_stores(asset_db)
    original = asset_db.scalar(select(AssetStore).where(AssetStore.bpcs_number == "B2"))
    assert original is not None
    original_id = original.id

    climate = create_asset(
        asset_db,
        original.id,
        ClimateAsset,
        ClimateAssetCreate(equipment_type="Split", capacity_btu=12000, location="Estoque"),
        "CLI",
    )

    # Simula a duplicata que a versão anterior poderia criar quando o SAP
    # aparecia depois do BPCS.
    duplicate = AssetStore(
        store_key="sap:s2",
        store_name="Loja Norte",
        bpcs_number="B2",
        sap_number="S2",
        praca="Mossoró",
    )
    asset_db.add(duplicate)
    asset_db.flush()
    fire = FireAsset(
        store_id=duplicate.id,
        asset_code="INC-s2-001",
        equipment_type="Extintor",
        location="Salão",
        status="Operacional",
    )
    asset_db.add(fire)

    upload = asset_db.scalar(select(Upload).limit(1))
    asset_db.add(
        Service(
            ticket="A-4",
            status="Em Aberto",
            store_name="Loja Norte",
            bpcs_number="B2",
            sap_number="S2",
            praca="Mossoró",
            upload_id=upload.id,
        )
    )
    asset_db.commit()

    sync_asset_stores(asset_db)

    stores = asset_db.scalars(select(AssetStore).where(AssetStore.bpcs_number == "B2")).all()
    assert len(stores) == 1
    merged = stores[0]
    assert merged.id == original_id
    assert merged.store_key == "sap:s2"
    assert merged.sap_number == "S2"
    assert asset_db.get(ClimateAsset, climate.id).store_id == merged.id
    assert asset_db.get(FireAsset, fire.id).store_id == merged.id


def test_optional_asset_fields_can_be_cleared(asset_db):
    from app.schemas.assets import ClimateAssetUpdate
    from app.services.assets import update_asset

    store = next(item for item in list_stores(asset_db) if item["sap_number"] == "S1")
    item = create_asset(
        asset_db,
        store["id"],
        ClimateAsset,
        ClimateAssetCreate(
            equipment_type="Cassete",
            capacity_btu=36000,
            location="Salão",
            brand="Carrier",
            serial_number="ABC-123",
        ),
        "CLI",
    )

    updated = update_asset(
        asset_db,
        ClimateAsset,
        item.id,
        ClimateAssetUpdate(brand=None, serial_number=None),
    )
    assert updated.brand is None
    assert updated.serial_number is None


def test_climate_capacity_is_required():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ClimateAssetCreate(equipment_type="Cassete", location="Salão")


def test_document_update_replaces_file_and_clears_metadata(asset_db, monkeypatch, tmp_path):
    import asyncio
    from io import BytesIO

    from fastapi import UploadFile
    from app.schemas.assets import StoreDocumentUpdate

    monkeypatch.setattr(assets_service, "ASSET_DOCUMENTS_DIR", str(tmp_path))
    store = list_stores(asset_db)[0]
    old_path = tmp_path / "old.pdf"
    old_path.write_bytes(b"old")
    document = StoreDocument(
        store_id=store["id"],
        document_type="AVCB",
        document_number="123",
        issuer="Corpo de Bombeiros",
        original_filename="old.pdf",
        stored_filename="old.pdf",
        mime_type="application/pdf",
        file_size=3,
    )
    asset_db.add(document)
    asset_db.commit()
    asset_db.refresh(document)

    upload = UploadFile(
        filename="novo.pdf",
        file=BytesIO(b"new-file"),
        headers={"content-type": "application/pdf"},
    )
    metadata = StoreDocumentUpdate(
        document_type="AVCB",
        custom_document_type=None,
        document_number=None,
        issue_date=None,
        expiration_date=None,
        issuer=None,
        notes=None,
    )
    result = asyncio.run(
        assets_service.update_document_record(asset_db, document, metadata, upload)
    )

    asset_db.refresh(document)
    assert result.original_filename == "novo.pdf"
    assert document.document_number is None
    assert document.issuer is None
    assert document.stored_filename != "old.pdf"
    assert not old_path.exists()
    assert (tmp_path / document.stored_filename).read_bytes() == b"new-file"


def test_store_filters_are_independent_from_current_search(asset_db):
    from app.services.assets import get_store_filters

    sync_asset_stores(asset_db)
    assert get_store_filters(asset_db)["pracas"] == ["Mossoró", "Natal"]
    # Uma busca restrita não altera as opções globais de praça.
    assert len(list_stores(asset_db, q="Centro")) == 1
    assert get_store_filters(asset_db)["pracas"] == ["Mossoró", "Natal"]


def test_list_stores_uses_aggregated_counts_without_n_plus_one(asset_db):
    from sqlalchemy import event

    sync_asset_stores(asset_db)
    engine = asset_db.get_bind()
    statements = []

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    try:
        stores = list_stores(asset_db)
    finally:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)

    assert len(stores) == 2
    # A quantidade de queries é fixa: não deve crescer uma query de documentos
    # para cada loja retornada.
    assert len(statements) <= 7
