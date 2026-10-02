"""Consulta de ativos no chat: dados, escopo e comprovante de acesso."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.models.asset_store import AssetStore
from app.models.climate_asset import ClimateAsset
from app.models.fire_asset import FireAsset
from app.models.water_asset import WaterAsset
from app.services.asset_query_access import issue_asset_query_token
from tests.api_harness import INTERNAL_KEY, SESSION_COOKIE, TestSession, fastapi_app, reset_database, seed_session


@pytest.fixture(autouse=True)
def clean():
    reset_database()
    yield
    reset_database()


@pytest.fixture
def inventory():
    db = TestSession()
    try:
        natal = AssetStore(store_key="natal", store_name="Natal Shopping", praca="Natal", bpcs_number="111")
        mossoro = AssetStore(store_key="mossoro", store_name="Mossoró Centro", praca="Mossoró", bpcs_number="222")
        db.add_all([natal, mossoro])
        db.flush()
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
        "session_id": "test-session", "access_token": issue_asset_query_token("test-session", 1),
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

    def fake_call(_session_id, _message, *, history, asset_access_token, asset_query_state, had_asset_context):
        captured.append((history, asset_access_token, asset_query_state))
        next_state = {"query_shape": "count", "asset_types": ["climatization"],
                      "store_name": "ER Parnamirim"} if asset_access_token else None
        return "Resposta de teste", next_state

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
    assert captured[0][1] is None
    assert isinstance(captured[1][1], str) and captured[1][1]
    follow_up = authorized_client.post("/assistant/chat", json={
        "conversation_id": authorized_conversation, "message": "E na praça Natal?",
    })
    assert follow_up.status_code == 200, follow_up.text
    assert [item["role"] for item in captured[2][0]] == ["user", "assistant"]
    assert captured[2][0][0]["content"] == "Quantos ativos?"
    assert captured[2][2] == {"query_shape": "count", "asset_types": ["climatization"],
                              "store_name": "ER Parnamirim"}


def test_asset_context_survives_a_service_routed_turn_in_between(monkeypatch):
    """Depois que o n8n roteia errado uma pergunta de acompanhamento para chamados,
    o contexto de ativos não pode se perder para as perguntas seguintes."""
    from app.api.routes import assistant

    captured = []

    def fake_call(_session_id, _message, *, history, asset_access_token, asset_query_state, had_asset_context):
        captured.append({"asset_access_token": asset_access_token, "asset_query_state": asset_query_state,
                         "had_asset_context": had_asset_context})
        if len(captured) == 1:
            return ("4 ativos encontrados",
                    {"query_shape": "count", "asset_types": ["climatization"], "store_name": "ER Parnamirim"})
        # O n8n roteou (incorretamente) para o fluxo de chamados e não devolve estado de ativos.
        return "Resposta do fluxo de chamados", None

    monkeypatch.setattr(assistant, "_call_n8n", fake_call)
    token, _ = seed_session(["assistant.use", "assets.view"], email="contexto@test.com")
    client = TestClient(fastapi_app, raise_server_exceptions=False)
    client.cookies.set(SESSION_COOKIE, token)

    r1 = client.post("/assistant/chat", json={"message": "Quantos ativos de climatização na ER Parnamirim?"})
    assert r1.status_code == 200, r1.text
    conversation_id = r1.json()["conversation_id"]

    r2 = client.post("/assistant/chat", json={
        "conversation_id": conversation_id, "message": "Quantos chamados estão em aberto?",
    })
    assert r2.status_code == 200, r2.text

    r3 = client.post("/assistant/chat", json={
        "conversation_id": conversation_id, "message": "E quantos splits tem lá?",
    })
    assert r3.status_code == 200, r3.text

    expected_state = {"query_shape": "count", "asset_types": ["climatization"], "store_name": "ER Parnamirim"}
    assert captured[0]["had_asset_context"] is False
    assert captured[1]["had_asset_context"] is True
    assert captured[1]["asset_query_state"] == expected_state
    assert captured[2]["had_asset_context"] is True
    assert captured[2]["asset_query_state"] == expected_state
