"""Filtro de lojas: várias praças, lojas marcadas e a lista leve de opções."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.models.asset_store import AssetStore
from tests.api_harness import SESSION_COOKIE, TestSession, fastapi_app, reset_database, seed_session
from tests.store_factory import add_asset_store


@pytest.fixture(autouse=True)
def clean():
    reset_database()
    yield
    reset_database()


@pytest.fixture
def lojas() -> dict[str, int]:
    db = TestSession()
    ids = {}
    for center_id, (nome, praca, bpcs, sap) in enumerate([
        ("Natal Shopping", "Natal", "111", "A1"), ("Midway", " Natal ", "112", "A2"),
        ("Mossoró Centro", "Mossoró", "113", "A3"), ("Fortaleza Sul", "Fortaleza", "114", "A4"),
        ("Loja Sem Praça", None, "115", "A5"),
    ], start=1):
        loja = add_asset_store(db, center_id, nome, praca=praca, bcps=bpcs, sap=sap)
        ids[nome] = loja.id
    db.commit()
    db.close()
    return ids


def cliente(permissoes=("assets.view",)) -> TestClient:
    token, _ = seed_session(list(permissoes))
    client = TestClient(fastapi_app, raise_server_exceptions=False)
    client.cookies.set(SESSION_COOKIE, token)
    return client


def nomes(resposta) -> list[str]:
    assert resposta.status_code == 200, resposta.text
    return [loja["store_name"] for loja in resposta.json()]


def test_sem_filtro_traz_todas_as_lojas_inclusive_sem_praca(lojas):
    assert len(nomes(cliente().get("/assets/stores"))) == 5


def test_varias_pracas_se_somam(lojas):
    resposta = cliente().get("/assets/stores", params=[("praca", "Natal"), ("praca", "Mossoró")])
    assert nomes(resposta) == ["Midway", "Mossoró Centro", "Natal Shopping"]


def test_praca_ignora_caixa_e_espacos(lojas):
    assert nomes(cliente().get("/assets/stores", params=[("praca", "  nAtal ")])) == ["Midway", "Natal Shopping"]


def test_lojas_marcadas_restringem_o_resultado(lojas):
    resposta = cliente().get("/assets/stores", params=[("store_id", lojas["Midway"]), ("store_id", lojas["Fortaleza Sul"])])
    assert nomes(resposta) == ["Fortaleza Sul", "Midway"]


def test_praca_e_loja_estreitam(lojas):
    dentro = cliente().get("/assets/stores", params=[("praca", "Natal"), ("store_id", lojas["Midway"])])
    assert nomes(dentro) == ["Midway"]
    fora = cliente().get("/assets/stores", params=[("praca", "Natal"), ("store_id", lojas["Mossoró Centro"])])
    assert nomes(fora) == []


def test_loja_sem_praca_sai_quando_uma_praca_e_marcada(lojas):
    assert "Loja Sem Praça" not in nomes(cliente().get("/assets/stores", params=[("praca", "Natal")]))


def test_praca_unica_e_busca_antigas_continuam_funcionando(lojas):
    assert nomes(cliente().get("/assets/stores", params={"praca": "Mossoró"})) == ["Mossoró Centro"]
    assert nomes(cliente().get("/assets/stores", params={"q": "midway"})) == ["Midway"]
    assert nomes(cliente().get("/assets/stores", params={"q": "A4"})) == ["Fortaleza Sul"]


def test_filtros_grandes_demais_sao_recusados(lojas):
    assert cliente().get("/assets/stores", params=[("store_id", i) for i in range(1001)]).status_code == 422
    assert cliente().get("/assets/stores", params=[("praca", f"p{i}") for i in range(101)]).status_code == 422
    assert cliente().get("/assets/stores", params={"store_id": "abc"}).status_code == 422


def test_opcoes_de_lojas_vem_leves_e_ordenadas(lojas):
    resposta = cliente().get("/assets/stores/options")
    assert resposta.status_code == 200
    opcoes = resposta.json()
    assert [o["name"] for o in opcoes] == ["Fortaleza Sul", "Loja Sem Praça", "Midway", "Mossoró Centro", "Natal Shopping"]
    midway = next(o for o in opcoes if o["name"] == "Midway")
    assert midway == {"id": lojas["Midway"], "name": "Midway", "praca": "Natal", "bpcs": "112", "sap": "A2"}
    assert next(o for o in opcoes if o["name"] == "Loja Sem Praça")["praca"] is None


def test_opcoes_e_filtros_exigem_sessao_e_permissao(lojas):
    sem_sessao = TestClient(fastapi_app, raise_server_exceptions=False)
    assert sem_sessao.get("/assets/stores/options").status_code == 401
    assert cliente(["assistant.use"]).get("/assets/stores/options").status_code == 403


def test_variantes_de_grafia_da_praca_valem_como_a_mesma(lojas):
    db = TestSession()
    add_asset_store(db, 6, "Ribeira", praca="Sao  Luis", bcps="201", sap="B1")
    add_asset_store(db, 7, "Cohama", praca="São Luís", bcps="202", sap="B2")
    db.commit()
    db.close()
    assert nomes(cliente().get("/assets/stores", params=[("praca", "São Luís")])) == ["Cohama", "Ribeira"]
    assert nomes(cliente().get("/assets/stores", params=[("praca", "sao luis")])) == ["Cohama", "Ribeira"]
    assert nomes(cliente().get("/assets/stores", params=[("praca", "São Luís"), ("praca", "Sao  Luis")])) == ["Cohama", "Ribeira"]
