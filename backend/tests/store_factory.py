"""Centros e lojas de inventário para testes de leitura e migração."""

from app.models.asset_store import AssetStore
from app.models.tape_center import TapeCenter
from app.models.upload import Upload


def add_center(db, record_id: int, name: str, *, bcps: str | None = None,
               sap: str | None = None, praca: str | None = None,
               status: str = "Aberta") -> TapeCenter:
    upload = Upload(source_file_name="test-dcentros", total_rows=1)
    db.add(upload)
    db.flush()
    center = TapeCenter(
        record_id=record_id, title=name, name=name, bcps_number=bcps,
        sap_number=sap, praca=praca, status=status, upload_id=upload.id,
    )
    db.add(center)
    db.flush()
    return center


def add_asset_store(db, record_id: int, name: str, *, bcps: str | None = None,
                    sap: str | None = None, praca: str | None = None,
                    status: str = "Aberta") -> AssetStore:
    center = add_center(db, record_id, name, bcps=bcps, sap=sap, praca=praca, status=status)
    store = AssetStore(tape_center_record_id=center.record_id)
    db.add(store)
    db.flush()
    return store
