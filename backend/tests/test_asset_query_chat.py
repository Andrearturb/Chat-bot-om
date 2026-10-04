"""Consulta de ativos no chat: dados, escopo e comprovante de acesso."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.models.asset_store import AssetStore
from app.models.climate_asset import ClimateAsset
from app.models.fire_asset import FireAsset
from app.models.water_asset import WaterAsset
from app.services.asset_query_access import issue_query_token
from tests.api_harness import INTERNAL_KEY, SESSION_COOKIE, TestSession, fastapi_app, reset_database, seed_session
from tests.store_factory import add_asset_store


@pytest.fixture(autouse=True)
def clean():
    reset_database()
    yield
    reset_database()


@pytest.fixture
def inventory():
    db = TestSession()
    try:
        natal = add_asset_store(db, 1, "Natal Shopping", praca="Natal", bcps="111", sap="999")
        mossoro = add_asset_store(db, 2, "Mossoró Centro", praca="Mossoró", bcps="222")
        db.add_all([
            ClimateAsset(store_id=natal.id, asset_code="CLI-001", equipment_type="Split",
                         capacity_btu=18000, location="Salão", brand="Springer", status="Operacional"),
            ClimateAsset(store_id=mossoro.id, asset_code="CLI-002", equipment_type="Split",
                         capacity_btu=12000, location="Estoque", status="Inoperacional"),
            FireAsset(store_id=natal.id, asset_code="INC-001", equipment_type="Extintor",
                      location="Corredor", expiration_date=date(2026, 10, 15), status="Operacional"),
            WaterAsset(store_id=natal.id, asset_code="AGU-001", equipment_type="Purificador",
                       location="Copa", next_filter_change=date(2026, 11, 1), status="Operacional"),
        ])
        db.commit()
    finally:
        db.close()


def query(**fields):
    payload = {
        "session_id": "test-session", "access_token": issue_query_token("test-session", 1, ["ativos"]),
        "query_shape": "count",
    }
    payload.update(fields)
    return TestClient(fastapi_app, raise_server_exceptions=False).post(
        "/chatbot/assets-query", json=payload, headers={"X-Internal-API-Key": INTERNAL_KEY}
    )


def test_count_filters_across_inventories(inventory):
    assert query().json()["total_count"] == 4
    assert query(asset_types=["climatization"], praca="Natal").json()["total_count"] == 1
    assert query(capacity_btu_min=15000).json()["total_count"] == 1
    assert query(status="Operacional").json()["total_count"] == 3
    salon = query(asset_types=["climatization"], location="salão de venda").json()
    assert salon["total_count"] == 1
    assert salon["matched_locations"] == [{"location": "Salão", "total": 1}]
    assert query(asset_types=["fire_safety", "water"], due_before="2026-10-31").json()["total_count"] == 1


def test_store_code_matches_bpcs_or_sap_number(inventory):
    """Um código de loja falado pelo usuário pode ser o número BPCS ou o SAP;
    a IA não sabe qual é qual sem consultar o cadastro, então o backend busca os dois."""
    assert query(store_code="111").json()["total_count"] == 3  # bpcs da Natal Shopping
    assert query(store_code="999").json()["total_count"] == 3  # sap da Natal Shopping
    assert query(store_code="222").json()["total_count"] == 1  # bpcs da Mossoró Centro
    assert query(store_code="nao-existe").json()["total_count"] == 0


def test_list_and_group_are_bounded(inventory):
    listed = query(query_shape="list", store_name="Natal", limit=2).json()
    assert listed["total_count"] == 3
    assert listed["truncated"] is True
    assert len(listed["rows"]) == 2
    assert {row["store_name"] for row in listed["rows"]} == {"Natal Shopping"}
    grouped = query(query_shape="group", group_by="asset_type").json()
    assert {row["asset_type"]: row["total"] for row in grouped["rows"]} == {
        "climatization": 2, "fire_safety": 1, "water": 1,
    }
    locations = query(query_shape="group", group_by="location", store_name="Natal").json()
    assert {row["location"] for row in locations["rows"]} == {"Salão", "Corredor", "Copa"}


def test_access_requires_header_and_signed_proof(inventory):
    assert TestClient(fastapi_app).post("/chatbot/assets-query", json={
        "session_id": "test-session", "access_token": "invalid", "query_shape": "count",
    }).status_code == 401
    assert query(access_token="invalid").status_code == 403
    assert query(session_id="other-session").status_code == 403
    assert query(query_shape="ranking").status_code == 422


def test_gateway_only_issues_asset_proof_with_permission(monkeypatch):
    from app.api.routes import assistant

    captured = []

    def fake_call(_session_id, _message, *, history, access_token, allowed_domains):
        captured.append((history, access_token, allowed_domains))
        return "Resposta de teste"

    monkeypatch.setattr(assistant, "_call_n8n", fake_call)
    authorized_client = None
    authorized_conversation = None
    for permissions in (["assistant.use"], ["assistant.use", "assets.view"]):
        token, _ = seed_session(permissions, email=f"{len(captured)}@test.com")
        client = TestClient(fastapi_app, raise_server_exceptions=False)
        client.cookies.set(SESSION_COOKIE, token)
        response = client.post("/assistant/chat", json={"message": "Quantos ativos?"})
        assert response.status_code == 200, response.text
        if "assets.view" in permissions:
            authorized_client = client
            authorized_conversation = response.json()["conversation_id"]
    # Sem permissão de domínio nenhuma: nem comprovante, nem domínio liberado.
    assert captured[0][1] is None
    assert captured[0][2] == []
    # Com assets.view: comprovante emitido cobrindo exatamente o domínio ativos.
    assert isinstance(captured[1][1], str) and captured[1][1]
    assert captured[1][2] == ["ativos"]
    follow_up = authorized_client.post("/assistant/chat", json={
        "conversation_id": authorized_conversation, "message": "E na praça Natal?",
    })
    assert follow_up.status_code == 200, follow_up.text
    assert [item["role"] for item in captured[2][0]] == ["user", "assistant"]
    assert captured[2][0][0]["content"] == "Quantos ativos?"
