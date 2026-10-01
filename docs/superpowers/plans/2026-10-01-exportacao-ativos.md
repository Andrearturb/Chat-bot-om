# Filtros de Praça/Loja e exportação de ativos — Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Filtrar as lojas da Central de Ativos por Praças e Lojas (múltipla escolha, que estreitam entre si) e exportar os equipamentos para uma planilha .xlsx, de todas as lojas ou só do filtro ativo.

**Architecture:** Um filtro único de lojas no servidor (`apply_store_filters`) serve a lista da tela e a exportação. A planilha é montada no servidor com openpyxl (uma aba por tipo de ativo). No frontend, um seletor de múltipla escolha reaproveitado para Praças e Lojas, mais uma janela "Exportar ativos" com prévia das contagens.

**Tech Stack:** FastAPI + SQLAlchemy + openpyxl (já no projeto), pytest; React 19 + Vite, `node --test`.

**Spec:** `docs/superpowers/specs/2026-10-01-exportacao-ativos-design.md` (leia antes de executar).

## Global Constraints

- Abas e cabeçalhos exatamente como na spec: abas `Climatização`, `Incêndio`, `Água`; colunas comuns `Loja · BPCS · SAP · Praça · Código · Tipo · Local`, depois as do tipo, depois `Status · Observações`.
- Arquivo `ativos-AAAA-MM-DD.xlsx` (data de `America/Fortaleza`); permissão `assets.view`; auditoria `ASSET_EXPORT` (entidade `asset_export`).
- Filtro: dentro de cada filtro os valores se somam; entre Praças, Lojas e `q` estreita (E). Limites: até 100 praças e 1000 lojas por consulta (422 acima disso).
- Texto de planilha é sempre gravado como texto (nunca fórmula); datas são datas do Excel (`DD/MM/YYYY`), anos e BTU são números.
- Mensagens e rótulos em português. Sem dependência nova. Sem IA.
- Testes do backend: `cd backend && ../.venv/Scripts/python.exe -m pytest -q`. Testes do frontend: `docker exec chatbot-frontend npm test`; lint: `docker exec chatbot-frontend npx oxlint`. O backend roda de uma imagem: depois de mudar código do backend, `docker compose up -d --build backend` antes de testar no navegador.
- Commits em português, terminados com `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Não editar arquivos do frontend durante uma execução de E2E (o Vite recarrega).

## Review Focus

1. Loja sem praça (`praca` nula ou vazia): continua aparecendo sem filtro, sai quando alguma praça é marcada. Teste na Tarefa 1.
2. Praça escrita com caixa ou espaços diferentes (`" natal "`): vale como a mesma. Teste na Tarefa 1.
3. Texto digitado que começa com `=`, `+`, `-` ou `@` nunca vira fórmula, nem no XML do arquivo. Teste na Tarefa 2.
4. Desmarcar uma praça tira do filtro as lojas que ficaram fora das praças restantes (sem filtro "fantasma" que esvazia a lista). Teste na Tarefa 3.
5. Sessão expirada ou servidor fora do ar durante o download: mensagem na própria janela, sem arquivo corrompido. Tratado na Tarefa 5.

---

## Mapa de arquivos

**Backend (`backend/`):** modificar `app/services/assets.py`, `app/schemas/assets.py`, `app/api/routes/assets.py`, `app/main.py`; criar `app/services/assets_export.py`, `app/api/routes/assets_export.py`, `tests/test_assets_filtros.py`, `tests/test_assets_export.py`.

**Frontend (`frontend/src/features/assets/`):** criar `filters.js`, `filters.test.js`, `components/MultiSelect.jsx`, `components/AssetFilters.jsx`, `components/ExportDialog.jsx`; modificar `api.js`, `AssetsPage.jsx`, `assets.css`; em `features/audit/`, modificar `auditLabels.js` e `audit.test.js`; modificar `frontend/package.json` (script de teste).

---

### Task 1: Filtro único de lojas e lista de opções (backend)

**Files:**
- Modify: `backend/app/services/assets.py` (substituir `list_stores`; acrescentar `apply_store_filters`, `list_store_options`)
- Modify: `backend/app/schemas/assets.py`, `backend/app/api/routes/assets.py`
- Create: `backend/tests/test_assets_filtros.py`

**Interfaces:**
- Produces: `apply_store_filters(query, db, *, q=None, praca=None, pracas=None, store_ids=None)`; `list_stores(db, q=None, praca=None, page=1, page_size=1000, *, sync=False, pracas=None, store_ids=None)`; `list_store_options(db) -> list[dict]`; `GET /assets/stores?praca=&praca=&store_id=&store_id=&q=`; `GET /assets/stores/options` → `[{id, name, praca, bpcs, sap}]`.

- [ ] **Step 1: Escrever os testes que vão falhar**

`backend/tests/test_assets_filtros.py`:

```python
"""Filtro de lojas: várias praças, lojas marcadas e a lista leve de opções."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.models.asset_store import AssetStore
from tests.api_harness import SESSION_COOKIE, TestSession, fastapi_app, reset_database, seed_session


@pytest.fixture(autouse=True)
def clean():
    reset_database()
    yield
    reset_database()


@pytest.fixture
def lojas() -> dict[str, int]:
    db = TestSession()
    ids = {}
    for nome, praca, bpcs, sap in [
        ("Natal Shopping", "Natal", "111", "A1"), ("Midway", " Natal ", "112", "A2"),
        ("Mossoró Centro", "Mossoró", "113", "A3"), ("Fortaleza Sul", "Fortaleza", "114", "A4"),
        ("Loja Sem Praça", None, "115", "A5"),
    ]:
        loja = AssetStore(store_key=nome.lower(), store_name=nome, praca=praca, bpcs_number=bpcs, sap_number=sap)
        db.add(loja)
        db.flush()
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
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && ../.venv/Scripts/python.exe -m pytest -q tests/test_assets_filtros.py`
Expected: FAIL (várias praças e `/stores/options` ainda não existem).

- [ ] **Step 3: Implementar o filtro compartilhado**

Em `backend/app/services/assets.py`, substitua a função `list_stores` inteira (do `def list_stores(` até o `return [store_response(store, counts) for store in stores]`) por:

```python
def _clean_pracas(praca: str | None, pracas: list[str] | None) -> list[str]:
    """Junta a praça única (antiga) com a lista; sem repetição por caixa/espaços."""
    unique: dict[str, str] = {}
    for value in [*(pracas or []), *([praca] if praca else [])]:
        text = (value or "").strip()
        if text:
            unique.setdefault(normalize_key(text), text)
    return list(unique.values())


def apply_store_filters(
    query,
    db: Session,
    *,
    q: str | None = None,
    praca: str | None = None,
    pracas: list[str] | None = None,
    store_ids: list[int] | None = None,
):
    """Filtro único das lojas (lista da tela e exportação).

    Dentro de cada filtro os valores se somam (praça A ou B). Entre filtros, estreita:
    praça marcada E loja marcada E texto da busca.
    """
    if q:
        pattern = f"%{q.strip()}%"
        # Use unaccent no PostgreSQL; SQLite usa ilike simples nos testes.
        is_postgres = db.bind.dialect.name == "postgresql" if db.bind else False
        if is_postgres:
            query = query.where(or_(
                func.unaccent(AssetStore.store_name).ilike(func.unaccent(pattern)),
                func.unaccent(AssetStore.bpcs_number).ilike(func.unaccent(pattern)),
                func.unaccent(AssetStore.sap_number).ilike(func.unaccent(pattern)),
                func.unaccent(AssetStore.praca).ilike(func.unaccent(pattern)),
            ))
        else:
            query = query.where(or_(
                AssetStore.store_name.ilike(pattern),
                AssetStore.bpcs_number.ilike(pattern),
                AssetStore.sap_number.ilike(pattern),
                AssetStore.praca.ilike(pattern),
            ))
    selected = _clean_pracas(praca, pracas)
    if selected:
        query = query.where(or_(*[
            func.lower(func.trim(AssetStore.praca)) == func.lower(func.trim(value)) for value in selected
        ]))
    if store_ids:
        query = query.where(AssetStore.id.in_(store_ids))
    return query


def list_stores(
    db: Session,
    q: str | None = None,
    praca: str | None = None,
    page: int = 1,
    page_size: int = 1000,
    *,
    sync: bool = False,
    pracas: list[str] | None = None,
    store_ids: list[int] | None = None,
) -> list[dict[str, Any]]:
    if sync or (db.scalar(select(func.count(AssetStore.id))) or 0) == 0:
        sync_asset_stores(db)
    query = apply_store_filters(
        select(AssetStore).order_by(AssetStore.store_name), db,
        q=q, praca=praca, pracas=pracas, store_ids=store_ids,
    )
    stores = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    counts = _all_count_maps(db)
    return [store_response(store, counts) for store in stores]


def list_store_options(db: Session) -> list[dict[str, Any]]:
    """Lista leve de lojas (sem contagens) para o seletor de Lojas."""
    if (db.scalar(select(func.count(AssetStore.id))) or 0) == 0:
        sync_asset_stores(db)
    stores = db.scalars(select(AssetStore).order_by(AssetStore.store_name)).all()
    return [
        {"id": store.id, "name": store.store_name, "praca": (store.praca or "").strip() or None,
         "bpcs": store.bpcs_number, "sap": store.sap_number}
        for store in stores
    ]
```

Em `backend/app/schemas/assets.py`, acrescente depois da classe `AssetStoreResponse`:

```python
class AssetStoreOptionResponse(BaseModel):
    id: int
    name: str
    praca: str | None
    bpcs: str | None
    sap: str | None
```

Em `backend/app/api/routes/assets.py`: acrescente `AssetStoreOptionResponse` ao import de `app.schemas.assets` e `list_store_options` ao import de `app.services.assets`; substitua a função `asset_stores` (a rota `GET /stores`) e acrescente a rota de opções logo depois da rota `/stores/filters` (antes de `/stores/{store_id}`):

```python
def _check_filter_sizes(praca: list[str] | None, store_id: list[int] | None) -> None:
    if (praca and (len(praca) > 100 or any(len(value) > 150 for value in praca))) or (store_id and len(store_id) > 1000):
        raise HTTPException(status_code=422, detail="Filtro grande demais.")


@router.get("/stores", response_model=list[AssetStoreResponse],
            dependencies=[Depends(require_permission("assets.view"))])
def asset_stores(q: str | None = Query(default=None, max_length=150),
                 praca: list[str] | None = Query(default=None),
                 store_id: list[int] | None = Query(default=None),
                 page: int = Query(default=1, ge=1),
                 page_size: int = Query(default=1000, ge=1, le=1000),
                 db: Session = Depends(get_db)):
    _check_filter_sizes(praca, store_id)
    return list_stores(db, q=q, pracas=praca, store_ids=store_id, page=page, page_size=page_size)
```

```python
@router.get("/stores/options", response_model=list[AssetStoreOptionResponse],
            dependencies=[Depends(require_permission("assets.view"))])
def asset_store_options(db: Session = Depends(get_db)):
    return list_store_options(db)
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd backend && ../.venv/Scripts/python.exe -m pytest -q`
Expected: todos passam (os testes antigos de `list_stores` continuam verdes).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/assets.py backend/app/schemas/assets.py backend/app/api/routes/assets.py backend/tests/test_assets_filtros.py
git commit -m "feat(ativos): filtro de lojas por várias praças e lojas marcadas

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Exportação para planilha (backend)

**Files:**
- Create: `backend/app/services/assets_export.py`, `backend/app/api/routes/assets_export.py`, `backend/tests/test_assets_export.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Consumes: `apply_store_filters`, `normalize_key` (Tarefa 1), `record_audit`.
- Produces: `GET /assets/export/preview` → `{"stores", "climatization", "fire_safety", "water"}`; `GET /assets/export` → .xlsx. Parâmetros repetidos: `praca`, `store_id`, `asset_type` (`climatization | fire_safety | water`). Erros em português: 400 sem lojas ou sem tipo; 422 tipo inválido.

- [ ] **Step 1: Escrever os testes que vão falhar**

`backend/tests/test_assets_export.py`:

```python
"""Exportação de ativos para .xlsx."""

from __future__ import annotations

import re
import zipfile
from datetime import date, datetime
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.models.asset_store import AssetStore
from app.models.auth import AuditLog
from app.models.climate_asset import ClimateAsset
from app.models.fire_asset import FireAsset
from app.models.water_asset import WaterAsset
from tests.api_harness import SESSION_COOKIE, TestSession, fastapi_app, reset_database, seed_session

CLIMATIZACAO = ["Loja", "BPCS", "SAP", "Praça", "Código", "Tipo", "Local", "Capacidade (BTU)", "Marca", "Modelo",
                "Nº de série", "Ano de fabricação", "Ano de instalação", "Tensão", "Gás refrigerante", "Status", "Observações"]
INCENDIO = ["Loja", "BPCS", "SAP", "Praça", "Código", "Tipo", "Local", "Agente extintor", "Capacidade",
            "Ano de fabricação", "Vencimento", "Teste hidrostático", "Status", "Observações"]
AGUA = ["Loja", "BPCS", "SAP", "Praça", "Código", "Tipo", "Local", "Marca", "Modelo", "Nº de série",
        "Ano de fabricação", "Ano de instalação", "Tensão", "Última troca de filtro", "Próxima troca de filtro",
        "Status", "Observações"]
FORMULA = '=HYPERLINK("http://exemplo.test","clique")'


@pytest.fixture(autouse=True)
def clean():
    reset_database()
    yield
    reset_database()


@pytest.fixture
def lojas() -> dict[str, int]:
    """Natal Shopping (4 equipamentos), Midway (1), Mossoró Centro (2) e Fortaleza Sul (nenhum)."""
    db = TestSession()
    ids = {}
    for nome, praca, bpcs, sap in [("Natal Shopping", "Natal", "111", "A1"), ("Midway", "Natal", "112", "A2"),
                                   ("Mossoró Centro", "Mossoró", "113", "A3"), ("Fortaleza Sul", "Fortaleza", "114", "A4")]:
        loja = AssetStore(store_key=nome.lower(), store_name=nome, praca=praca, bpcs_number=bpcs, sap_number=sap)
        db.add(loja)
        db.flush()
        ids[nome] = loja.id

    def clima(loja, codigo, local, **extra):
        db.add(ClimateAsset(store_id=ids[loja], asset_code=codigo, equipment_type="Split", capacity_btu=18000,
                            location=local, **extra))

    clima("Natal Shopping", "CLI-0002", "Sala de vendas", brand="Springer", model="Inverter", serial_number="SN-2")
    clima("Natal Shopping", "CLI-0001", FORMULA, notes="+cmd|' /C calc'!A0")
    db.add(FireAsset(store_id=ids["Natal Shopping"], asset_code="INC-0001", equipment_type="Extintor",
                     extinguisher_agent="PQS", capacity="6 kg", location="Corredor",
                     expiration_date=date(2027, 5, 10), manufacture_year=2023))
    db.add(WaterAsset(store_id=ids["Natal Shopping"], asset_code="AGU-0001", equipment_type="Purificador",
                      location="Copa", last_filter_change=date(2026, 3, 1)))
    clima("Midway", "CLI-0003", "Caixa")
    clima("Mossoró Centro", "CLI-0004", "Estoque")
    db.add(WaterAsset(store_id=ids["Mossoró Centro"], asset_code="AGU-0002", equipment_type="Gelágua", location="Refeitório"))
    db.commit()
    db.close()
    return ids


def cliente(permissoes=("assets.view",)) -> TestClient:
    token, _ = seed_session(list(permissoes))
    client = TestClient(fastapi_app, raise_server_exceptions=False)
    client.cookies.set(SESSION_COOKIE, token)
    return client


def baixar(client=None, params=None):
    return (client or cliente()).get("/assets/export", params=params or [])


def planilha(resposta):
    assert resposta.status_code == 200, resposta.text
    return load_workbook(BytesIO(resposta.content))


def linhas(ws) -> list[list]:
    return [[cell.value for cell in row] for row in ws.iter_rows(min_row=2)]


def test_traz_uma_aba_por_tipo_na_ordem_fixa(lojas):
    assert planilha(baixar()).sheetnames == ["Climatização", "Incêndio", "Água"]
    escolhidos = [("asset_type", "water"), ("asset_type", "climatization")]
    assert planilha(baixar(params=escolhidos)).sheetnames == ["Climatização", "Água"]


def test_cabecalhos_de_cada_aba(lojas):
    wb = planilha(baixar())
    for nome, esperado in (("Climatização", CLIMATIZACAO), ("Incêndio", INCENDIO), ("Água", AGUA)):
        assert [c.value for c in wb[nome][1]] == esperado


def test_linhas_ordenadas_por_loja_e_codigo(lojas):
    ws = planilha(baixar())["Climatização"]
    assert [(r[0], r[4]) for r in linhas(ws)] == [
        ("Midway", "CLI-0003"), ("Mossoró Centro", "CLI-0004"), ("Natal Shopping", "CLI-0001"), ("Natal Shopping", "CLI-0002")]


def test_dados_da_loja_e_do_equipamento_na_mesma_linha(lojas):
    linha = next(r for r in linhas(planilha(baixar())["Climatização"]) if r[4] == "CLI-0002")
    assert linha[:8] == ["Natal Shopping", "111", "A1", "Natal", "CLI-0002", "Split", "Sala de vendas", 18000]
    assert linha[8:11] == ["Springer", "Inverter", "SN-2"]
    assert linha[15] == "Operacional"


def test_datas_sao_datas_e_numeros_sao_numeros(lojas):
    ws = planilha(baixar())["Incêndio"]
    cabecalho = [c.value for c in ws[1]]
    linha = ws[2]
    vencimento = linha[cabecalho.index("Vencimento")]
    assert isinstance(vencimento.value, datetime) and vencimento.value.date() == date(2027, 5, 10)
    assert vencimento.number_format == "DD/MM/YYYY"
    assert linha[cabecalho.index("Ano de fabricação")].value == 2023
    assert linha[cabecalho.index("Teste hidrostático")].value is None   # vazio = célula vazia


def test_texto_com_formula_vira_texto_e_nunca_formula(lojas):
    resposta = baixar()
    ws = planilha(resposta)["Climatização"]
    linha = next(r for r in ws.iter_rows(min_row=2) if r[4].value == "CLI-0001")
    assert linha[6].value == FORMULA and linha[6].data_type == "s"
    assert linha[16].value == "+cmd|' /C calc'!A0" and linha[16].data_type == "s"
    with zipfile.ZipFile(BytesIO(resposta.content)) as arquivo:
        xml = "".join(arquivo.read(nome).decode("utf-8") for nome in arquivo.namelist() if nome.startswith("xl/worksheets/"))
    assert "<f>" not in xml and "<f " not in xml


def test_aba_sem_equipamentos_sai_so_com_o_cabecalho(lojas):
    resposta = baixar(params=[("praca", "Fortaleza")])
    wb = planilha(resposta)
    assert linhas(wb["Climatização"]) == [] and [c.value for c in wb["Climatização"][1]] == CLIMATIZACAO


def test_cabecalho_fixo_filtro_automatico_e_largura(lojas):
    ws = planilha(baixar())["Climatização"]
    assert ws.freeze_panes == "A2"
    assert ws.auto_filter.ref == ws.dimensions
    assert ws["A1"].font.bold and ws.column_dimensions["A"].width >= 10


def test_nome_do_arquivo_e_tipo(lojas):
    resposta = baixar()
    assert resposta.headers["content-type"].startswith("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    assert re.fullmatch(r'attachment; filename="ativos-\d{4}-\d{2}-\d{2}\.xlsx"', resposta.headers["content-disposition"])


def test_filtros_de_praca_e_loja_valem_na_exportacao(lojas):
    por_praca = baixar(params=[("praca", "Natal"), ("praca", "Mossoró")])
    assert {r[0] for r in linhas(planilha(por_praca)["Climatização"])} == {"Midway", "Mossoró Centro", "Natal Shopping"}
    estreito = baixar(params=[("praca", "Natal"), ("store_id", lojas["Midway"])])
    assert {r[0] for r in linhas(planilha(estreito)["Climatização"])} == {"Midway"}


def test_sem_lojas_ou_sem_tipo_da_400_e_tipo_invalido_da_422(lojas):
    vazio = baixar(params=[("praca", "Natal"), ("store_id", lojas["Mossoró Centro"])])
    assert vazio.status_code == 400 and "loja" in vazio.json()["detail"].lower()
    sem_tipo = baixar(params=[("asset_type", "")])
    assert sem_tipo.status_code == 400 and "tipo" in sem_tipo.json()["detail"].lower()
    assert baixar(params=[("asset_type", "ar-condicionado")]).status_code == 422
    assert cliente().get("/assets/export/preview", params=[("asset_type", "outro")]).status_code == 422


def test_previa_conta_lojas_e_ativos_por_tipo(lojas):
    previa = cliente().get("/assets/export/preview").json()
    assert previa == {"stores": 4, "climatization": 4, "fire_safety": 1, "water": 2}
    natal = cliente().get("/assets/export/preview", params=[("praca", "Natal")]).json()
    assert natal == {"stores": 2, "climatization": 3, "fire_safety": 1, "water": 1}
    so_clima = cliente().get("/assets/export/preview", params=[("asset_type", "climatization")]).json()
    assert so_clima == {"stores": 4, "climatization": 4, "fire_safety": 0, "water": 0}


@pytest.mark.parametrize("params", [[], [("praca", "Natal")], [("praca", "Mossoró"), ("asset_type", "water")]])
def test_contagem_da_previa_e_igual_as_linhas_do_arquivo(lojas, params):
    previa = cliente().get("/assets/export/preview", params=params).json()
    wb = planilha(baixar(params=params))
    chaves = {"Climatização": "climatization", "Incêndio": "fire_safety", "Água": "water"}
    for nome in wb.sheetnames:
        assert len(linhas(wb[nome])) == previa[chaves[nome]]


def test_exportacao_fica_na_auditoria(lojas):
    baixar(params=[("praca", "Natal")])
    db = TestSession()
    try:
        registro = db.query(AuditLog).filter_by(action="ASSET_EXPORT").one()
        assert registro.entity_type == "asset_export"
        assert registro.new_values["stores"] == 2 and registro.new_values["assets"] == 5
        assert registro.new_values["types"] == ["climatization", "fire_safety", "water"]
        assert registro.new_values["pracas"] == ["Natal"]
    finally:
        db.close()


def test_previa_nao_grava_auditoria(lojas):
    cliente().get("/assets/export/preview")
    db = TestSession()
    try:
        assert db.query(AuditLog).filter_by(action="ASSET_EXPORT").count() == 0
    finally:
        db.close()


def test_exige_sessao_e_permissao(lojas):
    anonimo = TestClient(fastapi_app, raise_server_exceptions=False)
    assert anonimo.get("/assets/export").status_code == 401
    assert anonimo.get("/assets/export/preview").status_code == 401
    sem_permissao = cliente(["assistant.use"])
    assert sem_permissao.get("/assets/export").status_code == 403
    assert sem_permissao.get("/assets/export/preview").status_code == 403
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && ../.venv/Scripts/python.exe -m pytest -q tests/test_assets_export.py`
Expected: FAIL (404 nas rotas novas).

- [ ] **Step 3: Implementar o serviço**

`backend/app/services/assets_export.py`:

```python
"""Exportação de ativos para planilha (.xlsx): filtro, contagens e montagem do arquivo."""

from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.asset_store import AssetStore
from app.models.climate_asset import ClimateAsset
from app.models.fire_asset import FireAsset
from app.models.water_asset import WaterAsset
from app.services.assets import apply_store_filters, normalize_key

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
TIMEZONE = ZoneInfo("America/Fortaleza")

# chave -> (modelo, nome da aba). A ordem daqui é a ordem das abas.
ASSET_TYPES = {
    "climatization": (ClimateAsset, "Climatização"),
    "fire_safety": (FireAsset, "Incêndio"),
    "water": (WaterAsset, "Água"),
}

# (cabeçalho, origem, atributo, tipo). Origem: "store" (loja) ou "asset" (equipamento).
_BEFORE = [
    ("Loja", "store", "store_name", "text"), ("BPCS", "store", "bpcs_number", "text"),
    ("SAP", "store", "sap_number", "text"), ("Praça", "store", "praca", "text"),
    ("Código", "asset", "asset_code", "text"), ("Tipo", "asset", "equipment_type", "text"),
    ("Local", "asset", "location", "text"),
]
_SPECIFIC = {
    "climatization": [
        ("Capacidade (BTU)", "capacity_btu", "int"), ("Marca", "brand", "text"), ("Modelo", "model", "text"),
        ("Nº de série", "serial_number", "text"), ("Ano de fabricação", "manufacture_year", "int"),
        ("Ano de instalação", "installation_year", "int"), ("Tensão", "voltage", "text"),
        ("Gás refrigerante", "refrigerant_gas", "text"),
    ],
    "fire_safety": [
        ("Agente extintor", "extinguisher_agent", "text"), ("Capacidade", "capacity", "text"),
        ("Ano de fabricação", "manufacture_year", "int"), ("Vencimento", "expiration_date", "date"),
        ("Teste hidrostático", "hydrostatic_test_date", "date"),
    ],
    "water": [
        ("Marca", "brand", "text"), ("Modelo", "model", "text"), ("Nº de série", "serial_number", "text"),
        ("Ano de fabricação", "manufacture_year", "int"), ("Ano de instalação", "installation_year", "int"),
        ("Tensão", "voltage", "text"), ("Última troca de filtro", "last_filter_change", "date"),
        ("Próxima troca de filtro", "next_filter_change", "date"),
    ],
}
_AFTER = [("Status", "asset", "status", "text"), ("Observações", "asset", "notes", "text")]

_HEADER_FONT = Font(bold=True, color="FFFFFF")
_HEADER_FILL = PatternFill("solid", fgColor="10183E")


def columns_for(type_key: str) -> list[tuple[str, str, str, str]]:
    return _BEFORE + [(header, "asset", attr, kind) for header, attr, kind in _SPECIFIC[type_key]] + _AFTER


def parse_types(values: list[str] | None) -> list[str]:
    """Tipos pedidos, na ordem fixa das abas. Ausente = todos."""
    if values is None:
        return list(ASSET_TYPES)
    cleaned = [value.strip() for value in values if value and value.strip()]
    if not cleaned:
        raise HTTPException(status_code=400, detail="Escolha ao menos um tipo de ativo.")
    invalid = [value for value in cleaned if value not in ASSET_TYPES]
    if invalid:
        raise HTTPException(status_code=422, detail=f"Tipo de ativo inválido: {invalid[0]}.")
    return [key for key in ASSET_TYPES if key in cleaned]


def select_stores(db: Session, *, pracas: list[str] | None, store_ids: list[int] | None) -> list[AssetStore]:
    query = apply_store_filters(select(AssetStore).order_by(AssetStore.store_name), db, pracas=pracas, store_ids=store_ids)
    return list(db.scalars(query).all())


def count_assets(db: Session, stores: list[AssetStore], types: list[str]) -> dict[str, int]:
    """Equipamentos por tipo nas lojas dadas (tipos não pedidos contam zero)."""
    ids = [store.id for store in stores]
    counts = {key: 0 for key in ASSET_TYPES}
    if not ids:
        return counts
    for key in types:
        model = ASSET_TYPES[key][0]
        counts[key] = db.scalar(select(func.count(model.id)).where(model.store_id.in_(ids))) or 0
    return counts


def export_filename() -> str:
    return f"ativos-{datetime.now(TIMEZONE):%Y-%m-%d}.xlsx"


def _write(ws, row: int, column: int, value, kind: str) -> None:
    if value is None or value == "":
        return
    cell = ws.cell(row=row, column=column)
    if kind == "date" and isinstance(value, (date, datetime)):
        cell.value = value
        cell.number_format = "DD/MM/YYYY"
    elif kind == "int" and isinstance(value, (int, float)):
        cell.value = value
    else:
        cell.value = str(value)
        cell.data_type = "s"   # sempre texto: o que começa com = + - @ nunca vira fórmula


def build_workbook(db: Session, stores: list[AssetStore], types: list[str]) -> bytes:
    by_id = {store.id: store for store in stores}
    workbook = Workbook()
    workbook.remove(workbook.active)
    for key in types:
        model, title = ASSET_TYPES[key]
        columns = columns_for(key)
        sheet = workbook.create_sheet(title)
        widths = []
        for index, (header, *_rest) in enumerate(columns, start=1):
            cell = sheet.cell(row=1, column=index, value=header)
            cell.font, cell.fill = _HEADER_FONT, _HEADER_FILL
            cell.alignment = Alignment(vertical="center")
            widths.append(len(header))
        assets = list(db.scalars(select(model).where(model.store_id.in_(list(by_id)))).all()) if by_id else []
        assets.sort(key=lambda asset: (normalize_key(by_id[asset.store_id].store_name), asset.asset_code))
        for row, asset in enumerate(assets, start=2):
            store = by_id[asset.store_id]
            for column, (_header, source, attr, kind) in enumerate(columns, start=1):
                value = getattr(store if source == "store" else asset, attr)
                _write(sheet, row, column, value, kind)
                if value is not None:
                    widths[column - 1] = max(widths[column - 1], len(str(value)))
        for column, width in enumerate(widths, start=1):
            sheet.column_dimensions[get_column_letter(column)].width = min(max(width + 2, 10), 50)
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
```

- [ ] **Step 4: Implementar as rotas e registrar**

`backend/app/api/routes/assets_export.py`:

```python
"""Exportação de ativos (.xlsx): prévia das contagens e download. Exige assets.view."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db, require_permission
from app.models.auth import AppUser
from app.services.assets_export import (
    XLSX_MEDIA_TYPE, build_workbook, count_assets, export_filename, parse_types, select_stores,
)
from app.services.auth import record_audit

router = APIRouter(prefix="/assets/export", tags=["Assets"],
                   dependencies=[Depends(require_permission("assets.view"))])


def _resolve(db: Session, praca: list[str] | None, store_id: list[int] | None, asset_type: list[str] | None):
    if (praca and (len(praca) > 100 or any(len(value) > 150 for value in praca))) or (store_id and len(store_id) > 1000):
        raise HTTPException(status_code=422, detail="Filtro grande demais.")
    types = parse_types(asset_type)
    return select_stores(db, pracas=praca, store_ids=store_id), types


@router.get("/preview")
def export_preview(praca: list[str] | None = Query(default=None), store_id: list[int] | None = Query(default=None),
                   asset_type: list[str] | None = Query(default=None), db: Session = Depends(get_db)) -> dict:
    stores, types = _resolve(db, praca, store_id, asset_type)
    return {"stores": len(stores), **count_assets(db, stores, types)}


@router.get("")
def export_assets(praca: list[str] | None = Query(default=None), store_id: list[int] | None = Query(default=None),
                  asset_type: list[str] | None = Query(default=None),
                  user: AppUser = Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
    stores, types = _resolve(db, praca, store_id, asset_type)
    if not stores:
        raise HTTPException(status_code=400, detail="Nenhuma loja encontrada com esses filtros.")
    counts = count_assets(db, stores, types)
    content = build_workbook(db, stores, types)
    record_audit(db, user_id=user.id, action="ASSET_EXPORT", entity_type="asset_export",
                 new_values={"stores": len(stores), "assets": sum(counts.values()), "types": types,
                             "pracas": praca or [], "store_ids": store_id or []})
    db.commit()
    return Response(content=content, media_type=XLSX_MEDIA_TYPE, headers={
        "Content-Disposition": f'attachment; filename="{export_filename()}"', "Cache-Control": "no-store"})
```

Em `backend/app/main.py`, junto dos outros imports de rotas acrescente
`from app.api.routes.assets_export import router as assets_export_router` e, junto dos `include_router`, `app.include_router(assets_export_router)`.

- [ ] **Step 5: Rodar e ver passar**

Run: `cd backend && ../.venv/Scripts/python.exe -m pytest -q`
Expected: todos passam, sem avisos.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/assets_export.py backend/app/api/routes/assets_export.py backend/app/main.py backend/tests/test_assets_export.py
git commit -m "feat(ativos): exportação de ativos para planilha .xlsx

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Regras e API do frontend (funções puras)

**Files:**
- Create: `frontend/src/features/assets/filters.js`, `frontend/src/features/assets/filters.test.js`
- Modify: `frontend/src/features/assets/api.js`, `frontend/package.json`, `frontend/src/features/audit/auditLabels.js`, `frontend/src/features/audit/audit.test.js`

**Interfaces:**
- Produces (`filters.js`): `EMPTY_FILTERS`, `ASSET_TYPE_OPTIONS`, `normalize`, `samePraca`, `isFiltered`, `storesForPracas(options, pracas)`, `pruneStoreIds(options, pracas, storeIds)`, `withPracas(filters, options, pracas)`, `matchesStore(option, text)`, `filtersParams(filters, params?)`, `exportParams(filters, types, scope)`, `storesCountLabel(shown, total)`, `exportSummary(preview, types)`. Opção de loja: `{ id, name, praca, bpcs, sap }`; filtros: `{ pracas: string[], storeIds: number[] }`; escopo: `"all" | "filtered"`.
- Produces (`api.js`): `fetchAssetStores({ q, pracas, storeIds, signal })`, `fetchStoreOptions({ signal })`, `fetchExportPreview({ filters, types, scope, signal })`, `downloadAssetsExport({ filters, types, scope, signal }) -> { blob, filename }`.

- [ ] **Step 1: Escrever os testes que vão falhar**

`frontend/src/features/assets/filters.test.js`:

```js
import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  EMPTY_FILTERS, exportParams, exportSummary, filtersParams, isFiltered, matchesStore, normalize,
  pruneStoreIds, samePraca, storesCountLabel, storesForPracas, withPracas,
} from './filters.js'

const options = [
  { id: 1, name: 'Natal Shopping', praca: 'Natal', bpcs: '111', sap: 'A1' },
  { id: 2, name: 'Midway', praca: 'Natal', bpcs: '112', sap: 'A2' },
  { id: 3, name: 'Mossoró Centro', praca: 'Mossoró', bpcs: '113', sap: 'A3' },
  { id: 4, name: 'Loja Sem Praça', praca: null, bpcs: '115', sap: 'A5' },
]

test('praças se comparam sem diferenciar caixa, acento ou espaços', () => {
  assert.ok(samePraca(' natal ', 'Natal'))
  assert.ok(samePraca('Mossoro', 'Mossoró'))
  assert.ok(!samePraca('Natal', 'Fortaleza'))
  assert.equal(normalize(null), '')
})

test('sem praça marcada o seletor de lojas oferece todas', () => {
  assert.equal(storesForPracas(options, []).length, 4)
})

test('com praças marcadas o seletor oferece só as lojas delas (a loja sem praça fica de fora)', () => {
  assert.deepEqual(storesForPracas(options, ['Natal', 'Mossoró']).map(o => o.id), [1, 2, 3])
  assert.deepEqual(storesForPracas(options, ['Natal']).map(o => o.id), [1, 2])
})

test('lojas marcadas que ficam fora das praças restantes saem do filtro', () => {
  assert.deepEqual(pruneStoreIds(options, ['Natal'], [1, 3]), [1])
  assert.deepEqual(pruneStoreIds(options, [], [1, 3, 4]), [1, 3, 4])
  const depois = withPracas({ pracas: ['Natal', 'Mossoró'], storeIds: [2, 3] }, options, ['Natal'])
  assert.deepEqual(depois, { pracas: ['Natal'], storeIds: [2] })
})

test('busca por nome, BPCS, SAP ou praça ignora acento e caixa', () => {
  assert.ok(matchesStore(options[2], 'mossoro'))
  assert.ok(matchesStore(options[0], '111'))
  assert.ok(matchesStore(options[1], 'a2'))
  assert.ok(matchesStore(options[0], 'NATAL'))
  assert.ok(!matchesStore(options[0], 'fortaleza'))
  assert.ok(matchesStore(options[0], '   '))
})

test('filtros viram parâmetros repetidos', () => {
  const params = filtersParams({ pracas: ['Natal', 'Mossoró'], storeIds: [2, 3] })
  assert.deepEqual(params.getAll('praca'), ['Natal', 'Mossoró'])
  assert.deepEqual(params.getAll('store_id'), ['2', '3'])
  assert.equal(filtersParams(EMPTY_FILTERS).toString(), '')
})

test('escopo "tudo" não manda filtros; "filtro ativo" manda', () => {
  const filters = { pracas: ['Natal'], storeIds: [1] }
  const tudo = exportParams(filters, ['water'], 'all')
  assert.equal(tudo.getAll('praca').length, 0)
  assert.deepEqual(tudo.getAll('asset_type'), ['water'])
  const filtrado = exportParams(filters, ['climatization', 'water'], 'filtered')
  assert.deepEqual(filtrado.getAll('praca'), ['Natal'])
  assert.deepEqual(filtrado.getAll('store_id'), ['1'])
  assert.deepEqual(filtrado.getAll('asset_type'), ['climatization', 'water'])
})

test('isFiltered e contagem de lojas', () => {
  assert.equal(isFiltered(EMPTY_FILTERS), false)
  assert.equal(isFiltered({ pracas: ['Natal'], storeIds: [] }), true)
  assert.equal(storesCountLabel(132, 132), '132 lojas')
  assert.equal(storesCountLabel(1, 1), '1 loja')
  assert.equal(storesCountLabel(12, 132), '12 de 132 lojas')
})

test('resumo da exportação só cita os tipos escolhidos', () => {
  const previa = { stores: 12, climatization: 40, fire_safety: 9, water: 3 }
  assert.equal(exportSummary(previa, ['climatization', 'fire_safety', 'water']), '12 lojas · 40 climatização · 9 incêndio · 3 água')
  assert.equal(exportSummary(previa, ['water']), '12 lojas · 3 água')
  assert.equal(exportSummary({ stores: 1, climatization: 0, fire_safety: 0, water: 0 }, ['water']), '1 loja · 0 água')
})
```

Em `frontend/src/features/audit/audit.test.js`, acrescente ao fim:

```js
test('exportação de ativos aparece na auditoria com o resumo', () => {
  assert.equal(actionLabel('ASSET_EXPORT'), 'Exportou ativos')
  assert.equal(entityLabel('asset_export'), 'Ativos')
  assert.equal(describeLog({ new_values: { stores: 12, assets: 52 } }), '12 lojas · 52 equipamentos')
  assert.equal(describeLog({ new_values: { stores: 1, assets: 1 } }), '1 loja · 1 equipamento')
})
```

Em `frontend/package.json`, no script `test`, acrescente `src/features/assets/filters.test.js` logo depois de `src/features/assets/assets.test.js`.

- [ ] **Step 2: Rodar e ver falhar**

Run: `docker exec chatbot-frontend npm test 2>&1 | grep -E "ERR_MODULE|^ℹ (pass|fail)"`
Expected: falha por `filters.js` inexistente e pelo teste de auditoria.

- [ ] **Step 3: Implementar**

`frontend/src/features/assets/filters.js`:

```js
/** Filtros da Central de Ativos (Praças e Lojas) e parâmetros da exportação: regras puras, sem React. */

export const EMPTY_FILTERS = { pracas: [], storeIds: [] }

export const ASSET_TYPE_OPTIONS = [
  { value: 'climatization', label: 'Climatização' },
  { value: 'fire_safety', label: 'Incêndio' },
  { value: 'water', label: 'Água' },
]

export function normalize(text) {
  return String(text ?? '').normalize('NFD').replace(/\p{M}/gu, '').toLowerCase().trim()
}

export function samePraca(a, b) {
  return normalize(a) === normalize(b)
}

export function isFiltered(filters) {
  return filters.pracas.length > 0 || filters.storeIds.length > 0
}

/** Lojas que o seletor oferece: só as das praças marcadas (todas, se nenhuma estiver marcada). */
export function storesForPracas(options, pracas) {
  if (pracas.length === 0) return options
  return options.filter(option => pracas.some(praca => samePraca(praca, option.praca)))
}

/** Tira das lojas marcadas as que ficaram fora das praças marcadas. */
export function pruneStoreIds(options, pracas, storeIds) {
  const allowed = new Set(storesForPracas(options, pracas).map(option => option.id))
  return storeIds.filter(id => allowed.has(id))
}

/** Troca as praças marcadas e mantém o filtro de lojas coerente. */
export function withPracas(filters, options, pracas) {
  return { pracas, storeIds: pruneStoreIds(options, pracas, filters.storeIds) }
}

export function matchesStore(option, text) {
  const needle = normalize(text)
  if (!needle) return true
  return [option.name, option.bpcs, option.sap, option.praca].some(value => normalize(value).includes(needle))
}

export function filtersParams(filters, params = new URLSearchParams()) {
  filters.pracas.forEach(praca => params.append('praca', praca))
  filters.storeIds.forEach(id => params.append('store_id', String(id)))
  return params
}

/** Parâmetros da exportação. Escopo "all" ignora os filtros da tela; "filtered" os envia. */
export function exportParams(filters, types, scope) {
  const params = new URLSearchParams()
  if (scope === 'filtered') filtersParams(filters, params)
  types.forEach(type => params.append('asset_type', type))
  return params
}

export function storesCountLabel(shown, total) {
  if (shown === total) return `${total} ${total === 1 ? 'loja' : 'lojas'}`
  return `${shown} de ${total} lojas`
}

export function exportSummary(preview, types) {
  const stores = `${preview.stores} ${preview.stores === 1 ? 'loja' : 'lojas'}`
  const parts = ASSET_TYPE_OPTIONS
    .filter(option => types.includes(option.value))
    .map(option => `${preview[option.value]} ${option.label.toLowerCase()}`)
  return [stores, ...parts].join(' · ')
}
```

Em `frontend/src/features/audit/auditLabels.js`: acrescente `ASSET_EXPORT: 'Exportou ativos',` ao objeto `ACTION_LABELS`, `asset_export: 'Ativos',` ao `ENTITY_LABELS` e substitua `describeLog` por:

```js
export function describeLog(log) {
  const values = { ...(log.old_values || {}), ...(log.new_values || {}) }
  const parts = [log.store_name, values.asset_code, values.filename].filter(Boolean)
  if (values.stores != null) {
    parts.push(`${values.stores} ${values.stores === 1 ? 'loja' : 'lojas'}`)
    if (values.assets != null) parts.push(`${values.assets} ${values.assets === 1 ? 'equipamento' : 'equipamentos'}`)
  }
  return parts.length ? parts.join(' · ') : '—'
}
```

Em `frontend/src/features/assets/api.js`: acrescente no topo `import { exportParams, filtersParams } from './filters.js'`, substitua `fetchAssetStores` e acrescente as novas funções (depois de `fetchAssetStore`):

```js
export function fetchAssetStores({ q = '', pracas = [], storeIds = [], signal } = {}) {
  const p = filtersParams({ pracas, storeIds })
  if (q.trim()) p.set('q', q.trim())
  return request(`/assets/stores${p.size ? `?${p}` : ''}`, { signal })
}

export const fetchStoreOptions = ({ signal } = {}) => request('/assets/stores/options', { signal })

export const fetchExportPreview = ({ filters, types, scope, signal } = {}) =>
  request(`/assets/export/preview?${exportParams(filters, types, scope)}`, { signal })

/** Baixa a planilha. Usa fetch direto (a resposta é um arquivo) e traduz os erros para mensagens. */
export async function downloadAssetsExport({ filters, types, scope, signal } = {}) {
  let response
  try {
    response = await fetch(`/assets/export?${exportParams(filters, types, scope)}`, { credentials: 'same-origin', signal })
  } catch (error) {
    if (error?.name === 'AbortError') throw error
    throw new AssetsApiError('Não foi possível conectar ao servidor.', { kind: 'network' })
  }
  if (!response.ok) {
    if (response.status === 401) throw new AssetsApiError('Sua sessão expirou. Entre novamente.', { status: 401 })
    let detail = ''
    try { detail = (await response.json())?.detail } catch { /* corpo sem JSON */ }
    throw new AssetsApiError(typeof detail === 'string' && detail ? detail : `Erro ${response.status}`, { status: response.status })
  }
  const filename = /filename="([^"]+)"/.exec(response.headers.get('content-disposition') || '')?.[1] || 'ativos.xlsx'
  return { blob: await response.blob(), filename }
}
```

(Remova a versão antiga de `fetchAssetStores`.)

- [ ] **Step 4: Rodar e ver passar**

Run: `docker exec chatbot-frontend npm test 2>&1 | grep -E "^ℹ (pass|fail)"`
Expected: `ℹ fail 0` (os testes novos entram na contagem).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/assets/filters.js frontend/src/features/assets/filters.test.js frontend/src/features/assets/api.js frontend/package.json frontend/src/features/audit/auditLabels.js frontend/src/features/audit/audit.test.js
git commit -m "feat(ativos): regras de filtro e chamadas da exportação no frontend

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Filtros de Praça e Loja na tela

**Files:**
- Create: `frontend/src/features/assets/components/MultiSelect.jsx`, `frontend/src/features/assets/components/AssetFilters.jsx`
- Modify: `frontend/src/features/assets/AssetsPage.jsx`, `frontend/src/features/assets/assets.css`

**Interfaces:**
- Consumes: `filters.js`, `api.js` (Tarefa 3).
- Produces: `<MultiSelect label options selected onChange allLabel unit filterOption? emptyText? />` com `options: [{ value, label, hint? }]`, `unit: [singular, plural]`; `<AssetFilters pracas storeOptions filters onChange shownCount searching />`.

Não há teste unitário de componente neste projeto (as regras já estão cobertas na Tarefa 3); a verificação é pelo build, pelo lint e pelo navegador (Tarefa 6).

- [ ] **Step 1: Criar os componentes**

`frontend/src/features/assets/components/MultiSelect.jsx`:

```jsx
import { useEffect, useMemo, useRef, useState } from "react";

/** Seletor de múltipla escolha com busca opcional. Vazio = "todos". */
export function MultiSelect({ label, options, selected, onChange, allLabel, unit, filterOption, emptyText = "Nada encontrado." }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const rootRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const onPointerDown = (event) => { if (!rootRef.current?.contains(event.target)) setOpen(false); };
    const onKeyDown = (event) => { if (event.key === "Escape") setOpen(false); };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const visible = useMemo(() => {
    if (!text.trim()) return options;
    return options.filter((option) => (filterOption
      ? filterOption(option, text)
      : String(option.label).toLowerCase().includes(text.trim().toLowerCase())));
  }, [options, text, filterOption]);

  const chosen = options.find((option) => selected.includes(option.value));
  const summary = selected.length === 0
    ? allLabel
    : selected.length === 1 ? (chosen?.label ?? `1 ${unit[0]}`) : `${selected.length} ${unit[1]}`;

  function toggle(value) {
    onChange(selected.includes(value) ? selected.filter((item) => item !== value) : [...selected, value]);
  }

  return (
    <div className="assets-multiselect" ref={rootRef}>
      <button
        type="button"
        className={`assets-multiselect__button${selected.length ? " is-active" : ""}`}
        aria-haspopup="true"
        aria-expanded={open}
        aria-label={label}
        onClick={() => { setOpen((value) => !value); setText(""); }}
      >
        <span className="assets-multiselect__label">{label}</span>
        <strong>{summary}</strong>
        <span aria-hidden="true">▾</span>
      </button>
      {open ? (
        <div className="assets-multiselect__panel" role="group" aria-label={label}>
          {options.length > 8 ? (
            <input type="search" value={text} onChange={(event) => setText(event.target.value)}
                   placeholder="Buscar..." aria-label={`Buscar em ${label}`} autoFocus />
          ) : null}
          <div className="assets-multiselect__list">
            {visible.length === 0 ? <p className="assets-multiselect__empty">{emptyText}</p> : visible.map((option) => (
              <label key={String(option.value)} className="assets-multiselect__option">
                <input type="checkbox" checked={selected.includes(option.value)} onChange={() => toggle(option.value)} />
                <span>{option.label}</span>
                {option.hint ? <small>{option.hint}</small> : null}
              </label>
            ))}
          </div>
          <div className="assets-multiselect__footer">
            <button type="button" onClick={() => onChange([])} disabled={selected.length === 0}>Limpar seleção</button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
```

`frontend/src/features/assets/components/AssetFilters.jsx`:

```jsx
import { EMPTY_FILTERS, isFiltered, matchesStore, storesCountLabel, storesForPracas, withPracas } from "../filters";
import { MultiSelect } from "./MultiSelect";

export function AssetFilters({ pracas, storeOptions, filters, onChange, shownCount, searching }) {
  const pracaChoices = pracas.map((praca) => ({ value: praca, label: praca }));
  const storeChoices = storesForPracas(storeOptions, filters.pracas).map((option) => ({
    value: option.id,
    label: option.name,
    hint: [option.praca, option.bpcs && `BPCS ${option.bpcs}`, option.sap && `SAP ${option.sap}`].filter(Boolean).join(" · "),
    option,
  }));
  const storeNames = new Map(storeOptions.map((option) => [option.id, option.name]));

  return (
    <>
      <div className="assets-filter-row">
        <MultiSelect
          label="Praças" options={pracaChoices} selected={filters.pracas} allLabel="Todas as praças"
          unit={["praça", "praças"]}
          onChange={(next) => onChange(withPracas(filters, storeOptions, next))}
        />
        <MultiSelect
          label="Lojas" options={storeChoices} selected={filters.storeIds} allLabel="Todas as lojas"
          unit={["loja", "lojas"]} emptyText="Nenhuma loja nessas praças."
          filterOption={(choice, text) => matchesStore(choice.option, text)}
          onChange={(next) => onChange({ ...filters, storeIds: next })}
        />
      </div>

      <div className="assets-search-meta" aria-live="polite">
        <span>
          <strong>{storesCountLabel(shownCount, Math.max(storeOptions.length, shownCount))}</strong>
          {searching ? " · atualizando resultados..." : ""}
        </span>
        {isFiltered(filters) ? (
          <div className="assets-active-filters">
            {filters.pracas.map((praca) => (
              <button key={`p-${praca}`} type="button" title="Remover praça"
                      onClick={() => onChange(withPracas(filters, storeOptions, filters.pracas.filter((item) => item !== praca)))}>
                Praça: {praca} <b aria-hidden="true">×</b>
              </button>
            ))}
            {filters.storeIds.map((id) => (
              <button key={`l-${id}`} type="button" title="Remover loja"
                      onClick={() => onChange({ ...filters, storeIds: filters.storeIds.filter((item) => item !== id) })}>
                Loja: {storeNames.get(id) ?? id} <b aria-hidden="true">×</b>
              </button>
            ))}
            <button className="assets-clear-filters" type="button" onClick={() => onChange(EMPTY_FILTERS)}>
              Limpar filtros
            </button>
          </div>
        ) : null}
      </div>
    </>
  );
}
```

- [ ] **Step 2: Estilos**

Acrescente ao fim de `frontend/src/features/assets/assets.css`:

```css
/* ── Filtros de Praças e Lojas (seletor de múltipla escolha) ───────────── */
.assets-filter-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  margin: 18px 0 12px;
}

.assets-multiselect {
  position: relative;
  min-width: 0;
}

.assets-multiselect__button {
  width: 100%;
  min-height: 46px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 14px;
  color: var(--assets-ink);
  border: 1px solid var(--assets-border);
  border-radius: 13px;
  background: #fff;
  font-size: 13px;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.18s, box-shadow 0.18s;
}

.assets-multiselect__label {
  color: var(--assets-muted);
  font-weight: 600;
}

.assets-multiselect__button strong {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.assets-multiselect__button:hover,
.assets-multiselect__button:focus-visible,
.assets-multiselect__button[aria-expanded="true"],
.assets-multiselect__button.is-active {
  border-color: #7cc5bf;
  box-shadow: 0 0 0 3px rgba(12, 116, 112, 0.09);
  outline: none;
}

.assets-multiselect__panel {
  position: absolute;
  z-index: 30;
  top: calc(100% + 6px);
  right: 0;
  left: 0;
  max-height: 340px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--assets-border);
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 18px 44px rgba(7, 26, 48, 0.16);
}

.assets-multiselect__panel input[type="search"] {
  min-height: 38px;
  margin: 10px;
  padding: 0 12px;
  border: 1px solid var(--assets-border);
  border-radius: 10px;
  font-size: 13px;
}

.assets-multiselect__list {
  min-height: 0;
  flex: 1;
  overflow-y: auto;
  padding: 4px 6px;
}

.assets-multiselect__option {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 2px 10px;
  align-items: center;
  padding: 8px 10px;
  border-radius: 9px;
  font-size: 13px;
  cursor: pointer;
}

.assets-multiselect__option:hover {
  background: #f4f9f9;
}

.assets-multiselect__option small {
  grid-column: 2;
  color: var(--assets-muted);
  font-size: 11px;
}

.assets-multiselect__empty {
  margin: 0;
  padding: 14px;
  color: var(--assets-muted);
  font-size: 13px;
  text-align: center;
}

.assets-multiselect__footer {
  display: flex;
  justify-content: flex-end;
  padding: 8px 12px;
  border-top: 1px solid var(--assets-border);
}

.assets-multiselect__footer button {
  color: var(--assets-blue);
  border: 0;
  background: transparent;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}

.assets-multiselect__footer button:disabled {
  opacity: 0.45;
  cursor: default;
}

.assets-section-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
}

@media (max-width: 760px) {
  .assets-filter-row {
    grid-template-columns: 1fr;
  }

  .assets-section-heading {
    flex-direction: column;
  }

  .assets-section-actions {
    justify-content: flex-start;
  }
}
```

- [ ] **Step 3: Ligar na tela de ativos**

Aplique estas edições em `frontend/src/features/assets/AssetsPage.jsx` (cada trecho "antes" aparece uma vez no arquivo; o arquivo usa aspas duplas e ponto e vírgula):

1. Importações. Troque `  fetchAssetSummary,\n  removeAsset,` por `  fetchAssetSummary,\n  fetchStoreOptions,\n  removeAsset,`. Troque `import { AssetsHero } from "./components/AssetsHero";` por:

```jsx
import { AssetFilters } from "./components/AssetFilters";
import { AssetsHero } from "./components/AssetsHero";
import { EMPTY_FILTERS, isFiltered } from "./filters";
```

2. Estado. Troque

```jsx
  const [query, setQuery] = useState("");
  const [praca, setPraca] = useState("");
```

por

```jsx
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [storeOptions, setStoreOptions] = useState([]);
```

3. `loadStores`. Substitua a função inteira (de `const loadStores = useCallback(async (search, region) => {` até `}, [query, praca]);`) por:

```jsx
  const loadStores = useCallback(async (nextFilters) => {
    const current = nextFilters ?? filters;
    searchControllerRef.current?.abort();
    const controller = new AbortController();
    searchControllerRef.current = controller;
    try {
      setSearching(true);
      setError("");
      const storeData = await fetchAssetStores({
        pracas: current.pracas, storeIds: current.storeIds, signal: controller.signal,
      });
      setStores(storeData);
    } catch (err) {
      if (err?.name !== "AbortError") setError(err.message);
    } finally {
      if (searchControllerRef.current === controller) {
        searchControllerRef.current = null;
        setSearching(false);
      }
    }
  }, [filters]);
```

4. Carga inicial. Troque

```jsx
        const [filtersData, storeData] = await Promise.all([
          fetchAssetStoreFilters({ signal: controller.signal }),
          fetchAssetStores({ signal: controller.signal }),
        ]);
        setPracas(filtersData?.pracas || []);
        setStores(storeData);
```

por

```jsx
        const [filtersData, storeData, optionsData] = await Promise.all([
          fetchAssetStoreFilters({ signal: controller.signal }),
          fetchAssetStores({ signal: controller.signal }),
          fetchStoreOptions({ signal: controller.signal }),
        ]);
        setPracas(filtersData?.pracas || []);
        setStores(storeData);
        setStoreOptions(optionsData || []);
```

5. Recarga ao mudar o filtro. Troque

```jsx
    const timer = window.setTimeout(() => loadStores(query, praca), 300);
    return () => window.clearTimeout(timer);
  }, [query, praca, loadStores]);
```

por

```jsx
    const timer = window.setTimeout(() => loadStores(filters), 150);
    return () => window.clearTimeout(timer);
  }, [filters, loadStores]);
```

6. `refreshStore`. Troque

```jsx
    const requests = [
      fetchAssetStores({ q: query, praca }),
      fetchAssetStoreFilters(),
    ];
    if (selectedStore) requests.push(fetchAssetStore(selectedStore.id));
    const [storeData, filtersData, detail] = await Promise.all(requests);
    setStores(storeData);
    setPracas(filtersData?.pracas || []);
```

por

```jsx
    const requests = [
      fetchAssetStores({ pracas: filters.pracas, storeIds: filters.storeIds }),
      fetchAssetStoreFilters(),
      fetchStoreOptions(),
    ];
    if (selectedStore) requests.push(fetchAssetStore(selectedStore.id));
    const [storeData, filtersData, optionsData, detail] = await Promise.all(requests);
    setStores(storeData);
    setPracas(filtersData?.pracas || []);
    setStoreOptions(optionsData || []);
```

7. Troque `const hasFilters = Boolean(query.trim() || praca);` por `const hasFilters = isFiltered(filters);`.

8. Troque o bloco da busca. Entre o marcador `<div className="assets-search-row">` (inclusive) e a linha `{error && stores.length > 0 ? <p className="assets-inline-error"` (exclusive) fica apenas:

```jsx
            <AssetFilters
              pracas={pracas}
              storeOptions={storeOptions}
              filters={filters}
              onChange={setFilters}
              shownCount={stores.length}
              searching={searching}
            />

```

9. No estado vazio, troque `onClick={() => { setQuery(""); setPraca(""); }}` por `onClick={() => setFilters(EMPTY_FILTERS)}`.

- [ ] **Step 4: Compilar, testar e checar o lint**

Run: `docker exec chatbot-frontend sh -c "npm test 2>&1 | grep -E '^ℹ (pass|fail)'; npx oxlint --format unix 2>&1 | grep -v '^$' | head -5; npm run build 2>&1 | grep -E 'built in|rror'"`
Expected: `ℹ fail 0`, nenhum aviso do lint e `✓ built`. Se o lint apontar `query`/`praca` não definidos, ainda sobrou uso do estado antigo: procure com `grep -n "query\|setPraca\|praca)" AssetsPage.jsx` e corrija.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/assets
git commit -m "feat(ativos): filtros de praças e lojas com múltipla escolha

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Janela "Exportar ativos"

**Files:**
- Create: `frontend/src/features/assets/components/ExportDialog.jsx`
- Modify: `frontend/src/features/assets/AssetsPage.jsx`, `frontend/src/features/assets/assets.css`

**Interfaces:**
- Consumes: `fetchExportPreview`, `downloadAssetsExport`, `ASSET_TYPE_OPTIONS`, `exportSummary`, `isFiltered`.
- Produces: `<ExportDialog filters filteredCount totalCount onClose onToast />`.

- [ ] **Step 1: Criar a janela**

`frontend/src/features/assets/components/ExportDialog.jsx`:

```jsx
import { useEffect, useRef, useState } from "react";
import { downloadAssetsExport, fetchExportPreview } from "../api";
import { ASSET_TYPE_OPTIONS, exportSummary, isFiltered } from "../filters";

function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function ExportDialog({ filters, filteredCount, totalCount, onClose, onToast }) {
  const filtered = isFiltered(filters);
  const [scope, setScope] = useState(filtered ? "filtered" : "all");
  const [types, setTypes] = useState(ASSET_TYPE_OPTIONS.map((option) => option.value));
  const [result, setResult] = useState({ key: null, preview: null, error: "" });
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState("");
  const closeRef = useRef(null);

  const key = `${scope}|${types.join(",")}`;

  useEffect(() => {
    closeRef.current?.focus();
    const onKeyDown = (event) => { if (event.key === "Escape" && !downloading) onClose(); };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose, downloading]);

  useEffect(() => {
    if (types.length === 0) return undefined;
    const controller = new AbortController();
    fetchExportPreview({ filters, types, scope, signal: controller.signal })
      .then((preview) => setResult({ key, preview, error: "" }))
      .catch((err) => { if (err?.name !== "AbortError") setResult({ key, preview: null, error: err.message }); });
    return () => controller.abort();
  }, [key, filters, types, scope]);

  const current = result.key === key ? result : null;
  const loading = types.length > 0 && !current;
  const preview = current?.preview ?? null;
  const canDownload = !downloading && types.length > 0 && Boolean(preview) && preview.stores > 0;

  function toggleType(value) {
    setTypes((previous) => (previous.includes(value) ? previous.filter((item) => item !== value) : [...previous, value]));
  }

  async function download() {
    setDownloading(true);
    setDownloadError("");
    try {
      const { blob, filename } = await downloadAssetsExport({ filters, types, scope });
      saveBlob(blob, filename);
      onToast({ kind: "success", message: `Planilha gerada: ${filename}` });
      onClose();
    } catch (err) {
      setDownloadError(err.message || "Não foi possível gerar a planilha.");
      setDownloading(false);
    }
  }

  return (
    <div className="assets-overlay assets-overlay--center" role="presentation"
         onMouseDown={(event) => { if (event.target === event.currentTarget && !downloading) onClose(); }}>
      <div className="assets-export" role="dialog" aria-modal="true" aria-labelledby="assets-export-title">
        <div className="assets-export__header">
          <h2 id="assets-export-title">Exportar ativos</h2>
          <button ref={closeRef} className="assets-export__close" type="button" onClick={onClose}
                  disabled={downloading} aria-label="Fechar">×</button>
        </div>

        <fieldset className="assets-export__group">
          <legend>Lojas</legend>
          <label>
            <input type="radio" name="export-scope" checked={scope === "all"} onChange={() => setScope("all")} />
            <span>Todas as lojas ({totalCount})</span>
          </label>
          <label className={filtered ? "" : "is-disabled"}>
            <input type="radio" name="export-scope" checked={scope === "filtered"} disabled={!filtered}
                   onChange={() => setScope("filtered")} />
            <span>Somente o filtro ativo ({filteredCount} {filteredCount === 1 ? "loja" : "lojas"})</span>
          </label>
        </fieldset>

        <fieldset className="assets-export__group">
          <legend>Ativos</legend>
          <label>
            <input type="checkbox" checked={types.length === ASSET_TYPE_OPTIONS.length}
                   onChange={() => setTypes(types.length === ASSET_TYPE_OPTIONS.length ? [] : ASSET_TYPE_OPTIONS.map((option) => option.value))} />
            <span>Todos</span>
          </label>
          {ASSET_TYPE_OPTIONS.map((option) => (
            <label key={option.value}>
              <input type="checkbox" checked={types.includes(option.value)} onChange={() => toggleType(option.value)} />
              <span>{option.label}</span>
            </label>
          ))}
          {types.length === 0 ? <p className="assets-export__hint">Escolha ao menos um tipo de ativo.</p> : null}
        </fieldset>

        <p className="assets-export__summary" role="status" aria-live="polite">
          {types.length === 0 ? "" : loading ? "Calculando..." : current?.error ? current.error : exportSummary(preview, types)}
        </p>
        {downloadError ? <p className="assets-export__error" role="alert">{downloadError}</p> : null}

        <div className="assets-drawer__actions">
          <button className="assets-button assets-button--quiet" type="button" onClick={onClose} disabled={downloading}>
            Cancelar
          </button>
          <button className="assets-button assets-button--primary" type="button" onClick={download} disabled={!canDownload}>
            {downloading ? "Gerando..." : "Baixar planilha"}
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Estilos**

Acrescente ao fim de `frontend/src/features/assets/assets.css`:

```css
/* ── Janela "Exportar ativos" ─────────────────────────────────────────── */
.assets-export {
  width: min(480px, calc(100vw - 32px));
  max-height: calc(100dvh - 32px);
  overflow-y: auto;
  padding: 26px;
  color: var(--assets-ink);
  border-radius: 22px;
  background: #fff;
  box-shadow: 0 30px 80px rgba(7, 26, 48, 0.28);
}

.assets-export__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}

.assets-export__header h2 {
  margin: 0;
  font-size: 22px;
  letter-spacing: -0.03em;
}

.assets-export__close {
  width: 34px;
  height: 34px;
  color: var(--assets-muted);
  border: 0;
  border-radius: 10px;
  background: #f4f7fb;
  font-size: 22px;
  line-height: 1;
  cursor: pointer;
}

.assets-export__group {
  display: grid;
  gap: 8px;
  margin: 0 0 16px;
  padding: 0;
  border: 0;
}

.assets-export__group legend {
  margin-bottom: 8px;
  padding: 0;
  color: var(--assets-muted);
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.assets-export__group label {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  border: 1px solid var(--assets-border);
  border-radius: 12px;
  font-size: 14px;
  cursor: pointer;
}

.assets-export__group label.is-disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.assets-export__hint,
.assets-export__error {
  margin: 0;
  font-size: 13px;
}

.assets-export__hint {
  color: #914c55;
}

.assets-export__error {
  padding: 9px 12px;
  color: #914c55;
  border: 1px solid #f0ced2;
  border-radius: 10px;
  background: #fff7f8;
}

.assets-export__summary {
  min-height: 22px;
  margin: 0 0 16px;
  padding: 10px 12px;
  color: #0b7270;
  border-radius: 12px;
  background: #f1fbfa;
  font-size: 13px;
  font-weight: 700;
}
```

- [ ] **Step 3: Botão e janela na tela**

Em `frontend/src/features/assets/AssetsPage.jsx`:

1. Importe a janela: depois de `import { AssetFilters } from "./components/AssetFilters";` acrescente `import { ExportDialog } from "./components/ExportDialog";`.
2. Estado: depois de `const [storeOptions, setStoreOptions] = useState([]);` acrescente `const [exportOpen, setExportOpen] = useState(false);`.
3. Troque `<span className="assets-section-mark" aria-hidden="true">● Base centralizada</span>` por:

```jsx
              <div className="assets-section-actions">
                <button className="assets-button assets-button--quiet" type="button" onClick={() => setExportOpen(true)}>
                  Exportar
                </button>
                <span className="assets-section-mark" aria-hidden="true">● Base centralizada</span>
              </div>
```

4. Depois de `<Toast toast={toast} />` acrescente:

```jsx
      {exportOpen ? (
        <ExportDialog
          filters={filters}
          filteredCount={stores.length}
          totalCount={storeOptions.length}
          onClose={() => setExportOpen(false)}
          onToast={setToast}
        />
      ) : null}
```

- [ ] **Step 4: Compilar, testar e checar o lint**

Run: `docker exec chatbot-frontend sh -c "npm test 2>&1 | grep -E '^ℹ (pass|fail)'; npx oxlint --format unix 2>&1 | grep -v '^$' | head -5; npm run build 2>&1 | grep -E 'built in|rror'"`
Expected: `ℹ fail 0`, lint sem avisos e `✓ built`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/assets
git commit -m "feat(ativos): janela para exportar ativos para planilha

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Verificação no navegador, documentação e fechamento

**Files:**
- Modify: `README.md`
- Create (descartável, fora do repositório, na pasta temporária da sessão): `export_check.py`

- [ ] **Step 1: Subir o backend novo**

```bash
docker compose up -d --build backend
curl -s -o /dev/null -w "backend: %{http_code}\n" http://localhost:8040/health/live
```

Expected: `backend: 200`.

- [ ] **Step 2: Verificar no navegador**

Crie o script de verificação (Playwright, usando o ambiente `.venv-e2e` do keycloak-central) e rode-o. Ele entra como `admin.om`, abre Ativos e confere o fluxo completo:

```python
"""Filtros de Praças/Lojas e exportação de ativos, de ponta a ponta no navegador."""
import re
import sys
import zipfile
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

APP, KC = "http://localhost:5173", "http://localhost:8081"
env = dict(l.split("=", 1) for l in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines() if "=" in l and not l.startswith("#"))
out = Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)

with sync_playwright() as pw:
    browser = pw.chromium.launch(channel="chrome", headless=True)
    for nome, viewport, mobile in (("desktop", {"width": 1440, "height": 900}, False), ("mobile", {"width": 390, "height": 844}, True)):
        context = browser.new_context(viewport=viewport, locale="pt-BR", accept_downloads=True, is_mobile=mobile, has_touch=mobile)
        page = context.new_page()
        erros = []
        page.on("pageerror", lambda e, erros=erros: erros.append(str(e)[:200]))
        page.goto(f"{APP}/login")
        page.get_by_role("button", name=re.compile(r"^Entrar")).click()
        page.wait_for_url(re.compile(rf"^({re.escape(KC)}/realms/|{re.escape(APP)}/$)"))
        if page.url.startswith(KC):
            page.fill("#username", "admin.om")
            page.fill("#password", env["DEV_ADMIN_PASSWORD"].strip())
            page.click("#kc-login")
        page.wait_for_url(f"{APP}/")
        page.locator('button[aria-label="Ativos"]').first.click()
        total = page.locator(".assets-store-card").count()
        expect(page.locator(".assets-store-card").first).to_be_visible()

        # Praças: marca as duas primeiras; o contador cai e aparecem as etiquetas
        page.get_by_role("button", name="Praças").click()
        caixas = page.locator('.assets-multiselect__panel input[type="checkbox"]')
        caixas.nth(0).check()
        caixas.nth(1).check()
        page.keyboard.press("Escape")
        page.wait_for_timeout(700)
        filtradas = page.locator(".assets-store-card").count()
        print(nome, "| lojas:", total, "->", filtradas, "| etiquetas:", page.locator(".assets-active-filters button").count() - 1)
        assert 0 < filtradas < total

        # Lojas: só oferece as das praças marcadas
        page.get_by_role("button", name="Lojas").click()
        oferecidas = page.locator('.assets-multiselect__panel input[type="checkbox"]').count()
        print("   lojas oferecidas no seletor:", oferecidas, "(<= filtradas:", oferecidas == filtradas, ")")
        assert oferecidas == filtradas
        page.locator('.assets-multiselect__panel input[type="checkbox"]').first.check()
        page.keyboard.press("Escape")
        page.wait_for_timeout(700)
        assert page.locator(".assets-store-card").count() == 1
        page.screenshot(path=str(out / f"ativos-filtrados-{nome}.png"))

        # Exportar o filtro ativo, só Climatização e Água
        page.get_by_role("button", name="Exportar").click()
        dialogo = page.get_by_role("dialog", name="Exportar ativos")
        expect(dialogo.get_by_role("radio", name=re.compile("Somente o filtro ativo"))).to_be_checked()
        dialogo.get_by_label("Incêndio").uncheck()
        expect(dialogo.get_by_role("status")).to_contain_text("1 loja")
        page.screenshot(path=str(out / f"exportar-{nome}.png"))
        with page.expect_download() as download:
            dialogo.get_by_role("button", name="Baixar planilha").click()
        arquivo = out / download.value.suggested_filename
        download.value.save_as(arquivo)
        with zipfile.ZipFile(arquivo) as z:
            abas = re.findall(r'<sheet [^>]*name="([^"]+)"', z.read("xl/workbook.xml").decode("utf-8"))
        print("   arquivo:", arquivo.name, "| abas:", abas)
        assert abas == ["Climatização", "Água"]

        # Limpar filtros e exportar tudo
        page.get_by_role("button", name="Limpar filtros").click()
        page.wait_for_timeout(700)
        assert page.locator(".assets-store-card").count() == total
        page.get_by_role("button", name="Exportar").click()
        expect(page.get_by_role("dialog", name="Exportar ativos").get_by_role("radio", name=re.compile("Somente o filtro ativo"))).to_be_disabled()
        page.keyboard.press("Escape")
        assert not erros, erros
        context.close()
    browser.close()
print("ok")
```

Run: `cd ../keycloak-central && .venv-e2e/Scripts/python.exe <pasta temporária>/export_check.py "$(pwd)/.env" <pasta temporária>/export-shots`
Expected: as linhas por tamanho de tela, `abas: ['Climatização', 'Água']` e `ok`. Abra as capturas `ativos-filtrados-*.png` e `exportar-*.png` para conferir o visual (seletores, etiquetas, janela, celular).

- [ ] **Step 3: Conferir o arquivo gerado e a auditoria**

Abra a planilha baixada e confira: cabeçalhos, formato de data e filtro automático. Abra Auditoria no app e confira a linha "Exportou ativos" com o resumo de lojas e equipamentos.

- [ ] **Step 4: Documentação**

Em `README.md`, na lista "Documentação", acrescente:

```markdown
- Central de Ativos: filtros por Praças e Lojas (múltipla escolha, estreitam entre si) e exportação para planilha .xlsx (uma aba por tipo de ativo). Design em `docs/superpowers/specs/2026-10-01-exportacao-ativos-design.md`.
```

- [ ] **Step 5: Verificação final e commit**

```bash
(cd backend && ../.venv/Scripts/python.exe -m pytest -q | tail -1)
docker exec chatbot-frontend sh -c "npm test 2>&1 | grep -E '^ℹ (pass|fail)'; npx oxlint 2>&1 | grep Found; npm run build 2>&1 | grep 'built in'"
git add README.md
git commit -m "docs: filtros e exportação da Central de Ativos

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

Expected: backend sem falhas e sem avisos, `ℹ fail 0`, lint com `0 warnings`, build ok.

Depois deste commit, siga com `superpowers:finishing-a-development-branch`.
