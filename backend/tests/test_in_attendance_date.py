"""Testes do campo de início de atendimento (Tape field 672479)."""

from datetime import datetime
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.session import get_db
from app.api.routes.services import router as services_router
from app.integrations.transformar_chamados import TapeTransformer
from app.models.service import Service
from app.services.importer import extrair_campos_negocio, sincronizar_servicos
from tests.conftest import make_linha


def test_transformer_captura_field_672479():
    transformer = TapeTransformer()
    record = {
        "record_id": "abc",
        "app_record_id": "5000",
        "created_on": "2026-09-25T08:00:00Z",
        "fields": [
            {
                "field_id": 672479,
                "label": "data_inicio_atendimento",
                "values": [{"value": "2026-09-25 09:10"}],
            }
        ],
    }

    transformed = transformer.transformar_record(record)

    assert transformed["field_values"]["in_attendance_date"]["field_id"] == 672479
    assert transformed["field_values"]["in_attendance_date"]["value"] == "2026-09-25 09:10"


def test_extrair_in_attendance_date():
    campos = extrair_campos_negocio(
        make_linha(ticket="5001", in_attendance_date="2026-09-25 09:10")
    )

    assert campos["in_attendance_date"] == datetime(2026, 9, 25, 9, 10)


def test_in_attendance_date_nulo():
    campos = extrair_campos_negocio(make_linha(ticket="5002", in_attendance_date=None))
    assert campos["in_attendance_date"] is None


def test_persiste_e_atualiza_in_attendance_date(db, upload, agora):
    primeira = make_linha(ticket="5003", in_attendance_date="2026-09-25 09:10")
    resultado = sincronizar_servicos(db, [primeira], upload.id, agora)
    db.flush()

    assert resultado["inserted"] == 1
    service = db.query(Service).filter_by(ticket="5003").one()
    assert service.in_attendance_date == datetime(2026, 9, 25, 9, 10)

    segunda = make_linha(ticket="5003", in_attendance_date="2026-09-25 10:30")
    resultado = sincronizar_servicos(db, [segunda], upload.id, agora)
    db.flush()

    assert resultado["updated"] == 1
    db.refresh(service)
    assert service.in_attendance_date == datetime(2026, 9, 25, 10, 30)


def test_services_api_expoe_in_attendance_date(db, upload):
    service = Service(
        ticket="5004",
        status="Concluído",
        praca="Natal",
        store_name="Loja Teste",
        in_attendance_date=datetime(2026, 9, 25, 9, 10),
        upload_id=upload.id,
    )
    db.add(service)
    db.commit()

    app = FastAPI()
    app.include_router(services_router)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)

    response = client.get("/services")

    assert response.status_code == 200
    payload = response.json()
    assert payload["dados"][0]["ticket"] == "5004"
    assert payload["dados"][0]["in_attendance_date"].startswith("2026-09-25T09:10:00")
