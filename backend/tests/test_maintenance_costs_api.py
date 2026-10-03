"""Portas de custos: duas credenciais no upload e leitura separada."""

import os
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.models.auth import AuditLog
from app.models.upload import Upload
from tests.api_harness import SESSION_COOKIE, TestSession, fastapi_app, reset_database, seed_session
from tests.test_maintenance_costs import workbook


@pytest.fixture(autouse=True)
def clean():
    reset_database()
    yield
    reset_database()


def client_with(permissions):
    token, _ = seed_session(permissions)
    client = TestClient(fastapi_app, raise_server_exceptions=False)
    client.cookies.set(SESSION_COOKIE, token)
    return client


def test_get_custos_exige_indicators_view():
    with TestClient(fastapi_app, raise_server_exceptions=False) as client:
        assert client.get("/maintenance-costs").status_code == 401
    with client_with([]) as client:
        assert client.get("/maintenance-costs").status_code == 403
    with client_with(["indicators.view"]) as client:
        assert client.get("/maintenance-costs").json() == {"dados": [], "upload_data": None}


def test_importacao_exige_chave_e_papel_e_registra_auditoria():
    content = workbook([41140014, "402124099", date(2026, 1, 1), None, 12, "101", "81", "4099", "Fornecedor", "Texto"])
    files = {"file": ("custos.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    with client_with(["sync.tape"]) as client:
        assert client.post("/imports/costs", files=files, headers={"x-api-key": "incorreta"}).status_code == 401
    with client_with([]) as client:
        assert client.post("/imports/costs", files=files, headers={"x-api-key": os.environ["API_KEY"]}).status_code == 403
    with client_with(["sync.tape"]) as client:
        response = client.post("/imports/costs", files=files, headers={"x-api-key": os.environ["API_KEY"]})
        assert response.status_code == 200, response.text
        assert response.json()["inserted"] == 1
    with TestSession() as db:
        upload = db.query(Upload).filter_by(source_type="maintenance_costs").one()
        assert upload.source_file_name == "custos.xlsx"
        assert db.query(AuditLog).filter_by(action="IMPORT_COSTS", entity_id=str(upload.id)).count() == 1
