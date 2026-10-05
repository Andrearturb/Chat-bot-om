"""Cada endpoint só aceita comprovante do próprio domínio."""

import pytest
from fastapi.testclient import TestClient

from app.services.asset_query_access import issue_query_token
from tests.api_harness import INTERNAL_KEY, fastapi_app, reset_database


@pytest.fixture(autouse=True)
def clean():
    reset_database()
    yield
    reset_database()


@pytest.mark.parametrize("path,domain", [
    ("/chatbot/preventive-query", "chamados_preventiva"),
    ("/chatbot/costs-query", "custos"),
])
def test_endpoint_exige_chave_e_dominio(path, domain):
    with TestClient(fastapi_app, raise_server_exceptions=False) as client:
        body = {"session_id": "sessao", "access_token": issue_query_token("sessao", 1, [domain]),
                "query_shape": "count"}
        assert client.post(path, json=body).status_code == 401
        wrong = {**body, "access_token": issue_query_token("sessao", 1, ["ativos"])}
        assert client.post(path, json=wrong, headers={"X-Internal-API-Key": INTERNAL_KEY}).status_code == 403
        response = client.post(path, json=body, headers={"X-Internal-API-Key": INTERNAL_KEY})
        assert response.status_code == 200, response.text
        assert response.json()["total_count"] == 0
