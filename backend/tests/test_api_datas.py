"""
Datas da API: o banco guarda UTC sem fuso; a API sempre envia com fuso ("Z").

Sem o fuso, o navegador lê a data como hora local e mostra horários 3 h adiantados
(ex.: a Auditoria mostrava 03:40 para um login feito às 00:40 em Fortaleza).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.dates import iso_utc, parse_api_datetime
from app.models.asset_store import AssetStore
from app.models.auth import AppUser, AssistantConversation, AssistantMessage, AuditLog
from tests.api_harness import SESSION_COOKIE, TestSession, fastapi_app, reset_database, seed_session

MOMENTO = datetime(2026, 10, 1, 3, 40, 42)   # UTC, como o banco guarda
ESPERADO = "2026-10-01T03:40:42Z"


@pytest.fixture(autouse=True)
def clean():
    reset_database()
    yield
    reset_database()


def cliente(permissoes) -> TestClient:
    token, _ = seed_session(permissoes)
    client = TestClient(fastapi_app, raise_server_exceptions=False)
    client.cookies.set(SESSION_COOKIE, token)
    return client


def test_iso_utc_marca_o_fuso():
    assert iso_utc(MOMENTO) == ESPERADO
    fortaleza = timezone(timedelta(hours=-3))
    assert iso_utc(datetime(2026, 10, 1, 0, 40, 42, tzinfo=fortaleza)) == ESPERADO
    assert iso_utc(None) is None


def test_auditoria_envia_a_data_com_fuso():
    client = cliente(["audit.view"])
    db = TestSession()
    db.add(AuditLog(action="LOGIN_SUCCESS", created_at=MOMENTO))
    db.commit()
    db.close()
    logs = client.get("/audit/logs").json()["logs"]
    assert logs[0]["created_at"] == ESPERADO


def test_conversas_enviam_as_datas_com_fuso():
    client = cliente(["assistant.use", "assistant.history"])
    db = TestSession()
    user = db.query(AppUser).filter_by(email="api@test.com").one()
    db.add(AssistantConversation(id="c1", user_id=user.id, n8n_session_id="s1", title="Teste",
                                 created_at=MOMENTO, updated_at=MOMENTO))
    db.add(AssistantMessage(id="m1", conversation_id="c1", role="user", content="oi", created_at=MOMENTO))
    db.commit()
    db.close()

    lista = client.get("/assistant/conversations").json()
    assert lista[0]["created_at"] == ESPERADO and lista[0]["updated_at"] == ESPERADO

    conversa = client.get("/assistant/conversations/c1").json()
    assert conversa["created_at"] == ESPERADO and conversa["updated_at"] == ESPERADO
    assert conversa["messages"][0]["created_at"] == ESPERADO


def test_limite_de_ia_informa_a_renovacao_com_fuso():
    client = cliente(["assistant.use"])
    uso = client.get("/auth/me").json()["ai_usage"]
    assert uso["resets_at"].endswith("Z")
    renovacao = datetime.fromisoformat(uso["resets_at"].replace("Z", "+00:00"))
    assert renovacao > datetime.now(timezone.utc)


def test_parse_api_datetime_normaliza_para_utc_sem_fuso():
    assert parse_api_datetime("2026-10-01T03:00:00.000Z") == datetime(2026, 10, 1, 3, 0, 0)
    assert parse_api_datetime("2026-10-01T00:00:00-03:00") == datetime(2026, 10, 1, 3, 0, 0)
    assert parse_api_datetime("2026-10-01T03:00:00") == datetime(2026, 10, 1, 3, 0, 0)   # sem fuso = UTC
    assert parse_api_datetime("ontem") is None
    assert parse_api_datetime("") is None and parse_api_datetime(None) is None


def test_auditoria_filtra_pelo_dia_local_enviado_em_utc():
    client = cliente(["audit.view"])
    db = TestSession()
    # 30/09 23:30 em Fortaleza = 01/10 02:30 UTC; 01/10 00:40 em Fortaleza = 01/10 03:40 UTC
    db.add(AuditLog(action="LOGOUT", created_at=datetime(2026, 10, 1, 2, 30)))
    db.add(AuditLog(action="LOGIN_SUCCESS", created_at=MOMENTO))
    db.commit()
    db.close()
    # O dia 01/10 em Fortaleza vai de 01/10 03:00 UTC até 02/10 02:59:59 UTC.
    resposta = client.get("/audit/logs", params={"date_from": "2026-10-01T03:00:00.000Z",
                                                 "date_to": "2026-10-02T02:59:59.999Z"})
    assert [log["action"] for log in resposta.json()["logs"]] == ["LOGIN_SUCCESS"]


def test_auditoria_envia_o_nome_da_loja():
    client = cliente(["audit.view"])
    db = TestSession()
    loja = AssetStore(store_key="acarau", store_name="Acaraú")
    db.add(loja)
    db.flush()
    db.add(AuditLog(action="ASSET_CREATE", entity_type="climate_asset", entity_id="12", store_id=loja.id,
                    new_values={"asset_code": "CLI-0001"}, created_at=MOMENTO))
    db.add(AuditLog(action="LOGIN_SUCCESS", entity_type="app_user", created_at=MOMENTO))
    db.commit()
    db.close()
    logs = {log["action"]: log for log in client.get("/audit/logs").json()["logs"]}
    assert logs["ASSET_CREATE"]["store_name"] == "Acaraú"
    assert logs["LOGIN_SUCCESS"]["store_name"] is None
