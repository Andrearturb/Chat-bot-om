# Painel de Chamados Corretivos — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preencher o card **Chamados Corretivos** da Central de Indicadores com o painel de manutenção corretiva do `bi-manutencao`, alimentado pela base de chamados que o chatbot-om já sincroniza da Tape.

**Architecture:** Três campos novos (`sla_late`, `approved_value`, `raw_status`) entram em `Service` pelo caminho de 6 passos que o `in_attendance_date` já percorreu: alias no `TapeTransformer` → extração no `importer` → coluna no modelo → `GET /services` → `dataAdapter`. O painel é um módulo React isolado em `features/indicators/corrective/`, com a lógica de KPI em funções puras testáveis e os componentes consumindo os registros que a `IndicatorsPage` já carrega.

**Tech Stack:** FastAPI, SQLAlchemy 2 (`Mapped`), Alembic, pytest · React 18 (Vite), recharts, `node:test`

**Spec:** `docs/superpowers/specs/2026-10-02-bi-manutencao-corretiva-design.md`

## Global Constraints

- Permissão: **`indicators.view`**, a que já existe. Nenhuma role nova no keycloak-central.
- **Não** remover nem alterar o normalizador de status do `importer.py`: `status` canônico continua servindo `structured_query.py` e o painel de Desempenho.
- **Não** alterar arquivos do painel de Desempenho além do `dataAdapter.js` e da linha de teste indicada na Task 4.
- Definição de **concluído** (SLA, custo médio, card Concluídos): `status == "Concluído"` (canônico). O `raw_status` só separa os cards de status.
- `sla_late` é **texto nulável** (`"Atrasado"` ou `None`), nunca booleano.
- Nos testes de `sla_late`, a entrada é o **HTML do badge** da Tape, nunca o texto achatado da planilha.
- Backend roda em container sem bind mount: depois de alterar `.py`, use `docker cp` + `docker restart chatbot-backend` para ver no navegador.
- Comando de teste do backend: `cd backend && ../.venv/Scripts/python.exe -m pytest -q`
- `tests/test_migracoes.py::test_banco_criado_antes_do_alembic_e_adotado_sem_perder_dados` **já falha antes deste plano** (espera baseline `0001`, encontra `0002`). Não é regressão deste trabalho e não deve ser "consertada" aqui.

## Review Focus

1. **`approved_value` igual a `0`** — 338 registros da fotografia têm valor aprovado zero. Um `if not valor` os descartaria; zero é valor legítimo e deve somar como zero. (Task 1)
2. **HTML do badge com caixa ou acento diferentes** (`ATRASADO`, `atrasado`) deve marcar atraso; a comparação é normalizada sem acento e sem caixa. (Task 1)
3. **`created_on` nulo com filtro de Mês/Ano ativo** — não deve quebrar nem oferecer opção `NaN` na lista de meses/anos. (Task 5)
4. **`raw_status` com texto novo da Tape** — entra no Total de Chamados e em nenhum card de status, sem quebrar e sem somar errado. (Task 5)
5. **`signature_status` com texto inesperado** (nem "conclu" nem "pend") — não conta em Total de O.S. (Task 6)

---

## Estrutura de arquivos

**Backend**

| Arquivo | Responsabilidade |
|---|---|
| `backend/app/services/importer.py` | *modificar* — dois helpers de derivação, `CAMPOS_SINCRONIZADOS`, `extrair_campos_negocio` |
| `backend/app/integrations/transformar_chamados.py` | *modificar* — aliases de `sla_late` e `approved_value` |
| `backend/app/models/service.py` | *modificar* — três colunas |
| `backend/migrations/versions/20261002_0003_corretiva_sla_valor.py` | *criar* — migração `0003` |
| `backend/app/schemas/service.py` | *modificar* — três campos na resposta |
| `backend/app/api/routes/services.py` | *modificar* — três campos no mapeamento |
| `backend/tests/conftest.py` | *modificar* — `make_linha` aceita os campos novos |
| `backend/tests/test_corretiva_sla_valor.py` | *criar* — cobertura de 6 passos dos três campos |

**Frontend**

| Arquivo | Responsabilidade |
|---|---|
| `frontend/src/features/indicators/dataAdapter.js` | *modificar* — renomear `rawStatus`→`canonicalStatus`, expor os três campos |
| `frontend/src/features/indicators/indicators.test.js` | *modificar* — uma asserção |
| `frontend/src/features/indicators/corrective/correctiveData.js` | *criar* — toda a lógica de cálculo, funções puras |
| `frontend/src/features/indicators/corrective/corrective.test.js` | *criar* — testes da lógica |
| `frontend/src/features/indicators/corrective/CorrectivePanel.jsx` | *criar* — composição do painel |
| `frontend/src/features/indicators/corrective/components/CorrectiveFilters.jsx` | *criar* — seis seletores |
| `frontend/src/features/indicators/corrective/components/CorrectiveKpis.jsx` | *criar* — 4 KPIs + 5 cards de status |
| `frontend/src/features/indicators/corrective/components/CorrectiveCharts.jsx` | *criar* — analistas e série mensal |
| `frontend/src/features/indicators/corrective/components/CorrectiveRankTables.jsx` | *criar* — rankings de loja e categoria |
| `frontend/src/features/indicators/corrective/components/CorrectiveDetailModal.jsx` | *criar* — drill-down |
| `frontend/src/features/indicators/IndicatorsPage.jsx` | *modificar* — encaixe do painel e chave de estado |
| `frontend/src/features/indicators/indicators.css` | *modificar* — estilos escopados |
| `frontend/package.json` | *modificar* — script `test:corrective` |

**Docs**

| Arquivo | Responsabilidade |
|---|---|
| `docs/integracao-bi-corretiva.md` | *criar* — validação ao vivo contra a fotografia |

---

## Task 1: Helpers de derivação no importer

Duas funções puras: uma lê a marca de atraso de dentro do HTML da Tape, outra converte o valor aprovado em número.

**Files:**
- Modify: `backend/app/services/importer.py` (acrescentar após `normalizar_status`, que termina na linha 211)
- Test: `backend/tests/test_corretiva_sla_valor.py` (criar)

**Interfaces:**
- Consumes: `normalizar_texto(valor: object) -> str | None`, já existente no mesmo arquivo
- Produces:
  - `derivar_sla_atrasado(valor: object) -> str | None` — devolve `"Atrasado"` ou `None`
  - `converter_decimal(valor: object) -> Decimal | None`

- [ ] **Step 1: Escrever o teste que falha**

Criar `backend/tests/test_corretiva_sla_valor.py`:

```python
"""Testes dos campos de SLA, valor aprovado e status cru da manutenção corretiva."""

from decimal import Decimal
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from app.services.importer import converter_decimal, derivar_sla_atrasado


BADGE_ATRASADO = (
    '<div><div style="background-color:#ff0000;color: #fff;border: none;'
    'text-align: center;padding: 10px 20px;border-radius: 5px;font-size: 16px;'
    'width: 70px;height: 12px;">Atrasado</div></div>'
)


def test_sla_atrasado_vem_de_dentro_do_html():
    """A Tape devolve a marca como badge HTML, não como texto puro."""
    assert derivar_sla_atrasado(BADGE_ATRASADO) == "Atrasado"


def test_sla_atrasado_tolera_caixa_e_acento():
    assert derivar_sla_atrasado("<div>ATRASADO</div>") == "Atrasado"
    assert derivar_sla_atrasado("<div>atrasado</div>") == "Atrasado"
    assert derivar_sla_atrasado("Atrasado") == "Atrasado"


def test_sla_sem_marca_e_nulo():
    assert derivar_sla_atrasado(None) is None
    assert derivar_sla_atrasado("") is None
    assert derivar_sla_atrasado("<div></div>") is None
    assert derivar_sla_atrasado("<p>📦0 dia(s) passado(s) de 3 dia(s) - 0%</p>") is None


def test_valor_aprovado_converte_numero():
    assert converter_decimal("350") == Decimal("350")
    assert converter_decimal(150) == Decimal("150")
    assert converter_decimal("1.234,56") == Decimal("1234.56")


def test_valor_aprovado_zero_nao_vira_nulo():
    """338 registros da fotografia têm valor zero: zero é valor, não ausência."""
    assert converter_decimal(0) == Decimal("0")
    assert converter_decimal("0") == Decimal("0")


def test_valor_aprovado_ilegivel_e_nulo():
    assert converter_decimal(None) is None
    assert converter_decimal("") is None
    assert converter_decimal("sem valor") is None
```

- [ ] **Step 2: Rodar o teste para confirmar que falha**

Run: `cd backend && ../.venv/Scripts/python.exe -m pytest -q tests/test_corretiva_sla_valor.py`
Expected: FAIL com `ImportError: cannot import name 'converter_decimal'`

- [ ] **Step 3: Implementar os dois helpers**

Em `backend/app/services/importer.py`, acrescentar ao bloco de imports do topo:

```python
import re
import unicodedata
from decimal import Decimal, InvalidOperation
```

(Se `re` já estiver importado, não duplique.)

Acrescentar as funções depois de `normalizar_status`:

```python
def derivar_sla_atrasado(valor: object) -> str | None:
    """Lê a marca de atraso do campo 620293, que a Tape devolve como badge HTML.

    A planilha exportada achata o badge para o texto "Atrasado", mas a API
    entrega '<div ...>Atrasado</div>'. Comparar por igualdade marcaria zero
    chamados como atrasados.
    """
    texto = normalizar_texto(valor)

    if texto is None:
        return None

    sem_tags = re.sub(r"<[^>]*>", " ", texto)
    sem_acento = "".join(
        caractere
        for caractere in unicodedata.normalize("NFKD", sem_tags)
        if not unicodedata.combining(caractere)
    )

    return "Atrasado" if "atrasado" in sem_acento.lower() else None


def converter_decimal(valor: object) -> Decimal | None:
    """Converte o valor aprovado em número. Zero é valor válido, não ausência."""
    if valor is None:
        return None

    if isinstance(valor, bool):
        return None

    if isinstance(valor, (int, float, Decimal)):
        return Decimal(str(valor))

    texto = normalizar_texto(valor)

    if texto is None:
        return None

    # "1.234,56" (formato brasileiro) e "1234.56" chegam ao mesmo número.
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")

    try:
        return Decimal(texto)
    except InvalidOperation:
        return None
```

- [ ] **Step 4: Rodar o teste para confirmar que passa**

Run: `cd backend && ../.venv/Scripts/python.exe -m pytest -q tests/test_corretiva_sla_valor.py`
Expected: PASS, 6 passed

- [ ] **Step 5: Rodar a suíte inteira**

Run: `cd backend && ../.venv/Scripts/python.exe -m pytest -q`
Expected: tudo passa, **exceto** a falha pré-existente de `test_migracoes.py` descrita nas Global Constraints

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/importer.py backend/tests/test_corretiva_sla_valor.py
git commit -m "feat(backend): helpers de SLA atrasado e valor aprovado da corretiva"
```

---

## Task 2: Aliases, colunas e persistência

Os campos passam a ser capturados da Tape, persistidos e comparados na sincronização.

**Files:**
- Modify: `backend/app/integrations/transformar_chamados.py` (`FIELD_ALIASES`, que termina na linha 151)
- Modify: `backend/app/models/service.py`
- Modify: `backend/app/services/importer.py` (`CAMPOS_SINCRONIZADOS` linhas 42-63, `extrair_campos_negocio` linhas 364-440)
- Create: `backend/migrations/versions/20261002_0003_corretiva_sla_valor.py`
- Modify: `backend/tests/conftest.py` (`make_linha`, linhas 60-85)
- Test: `backend/tests/test_corretiva_sla_valor.py`

**Interfaces:**
- Consumes: `derivar_sla_atrasado`, `converter_decimal` (Task 1); `obter_valor_campo(linha, chave, field_id=None)`; `obter_field_id_por_alias(alias) -> int | None`
- Produces:
  - `Service.sla_late: str | None`, `Service.approved_value: Decimal | None`, `Service.raw_status: str | None`
  - `extrair_campos_negocio` passa a devolver as chaves `sla_late`, `approved_value`, `raw_status`
  - `make_linha(..., sla_late=None, approved_value=None)`

**ATENÇÃO — não crie alias para `raw_status`.** O `FIELD_ALIAS_INDEX` mapeia `field_id → alias` um-para-um (`construir_indice_aliases`, linhas 155-168 de `transformar_chamados.py`). Declarar `raw_status` com o mesmo campo `580453` do `status` sobrescreveria um dos dois e um deles sumiria do `field_values`. O `raw_status` é derivado do **mesmo** alias `status`, antes da normalização.

- [ ] **Step 1: Escrever os testes que falham**

Acrescentar ao fim de `backend/tests/test_corretiva_sla_valor.py`:

```python
from datetime import datetime

from app.integrations.transformar_chamados import TapeTransformer
from app.models.service import Service
from app.services.importer import extrair_campos_negocio, sincronizar_servicos
from tests.conftest import make_linha


def test_transformer_captura_campos_620293_e_613329():
    transformer = TapeTransformer()
    record = {
        "record_id": "abc",
        "app_record_id": "7000",
        "created_on": "2026-09-25T08:00:00Z",
        "fields": [
            {"field_id": 620293, "label": "  ", "values": [{"value": BADGE_ATRASADO}]},
            {"field_id": 613329, "label": "Valor Aprovado", "values": [{"value": "350"}]},
        ],
    }

    transformed = transformer.transformar_record(record)

    assert transformed["field_values"]["sla_late"]["field_id"] == 620293
    assert transformed["field_values"]["sla_late"]["value"] == BADGE_ATRASADO
    assert transformed["field_values"]["approved_value"]["value"] == "350"


def test_extrai_sla_valor_e_status_cru():
    campos = extrair_campos_negocio(
        make_linha(
            ticket="7001",
            status="Chamado Concluído",
            sla_late=BADGE_ATRASADO,
            approved_value="350",
        )
    )

    assert campos["sla_late"] == "Atrasado"
    assert campos["approved_value"] == Decimal("350")
    # O status cru preserva o texto da Tape; o canônico continua normalizado.
    assert campos["raw_status"] == "Chamado Concluído"
    assert campos["status"] == "Concluído"


def test_solicitacao_finalizada_mantem_cru_e_vira_concluido():
    campos = extrair_campos_negocio(
        make_linha(ticket="7002", status="Solicitação Finalizada")
    )

    assert campos["raw_status"] == "Solicitação Finalizada"
    assert campos["status"] == "Concluído"


def test_campos_novos_nulos():
    campos = extrair_campos_negocio(
        make_linha(ticket="7003", sla_late=None, approved_value=None)
    )

    assert campos["sla_late"] is None
    assert campos["approved_value"] is None


def test_persiste_e_atualiza_campos_novos(db, upload, agora):
    primeira = make_linha(
        ticket="7004", status="Chamado Concluído",
        sla_late=BADGE_ATRASADO, approved_value="350",
    )
    resultado = sincronizar_servicos(db, [primeira], upload.id, agora)
    db.flush()

    assert resultado["inserted"] == 1
    service = db.query(Service).filter_by(ticket="7004").one()
    assert service.sla_late == "Atrasado"
    assert service.approved_value == Decimal("350.00")
    assert service.raw_status == "Chamado Concluído"

    # Sai do atraso e o valor muda: os três campos entram na comparação.
    segunda = make_linha(
        ticket="7004", status="Solicitação Finalizada",
        sla_late=None, approved_value="420",
    )
    resultado = sincronizar_servicos(db, [segunda], upload.id, agora)
    db.flush()

    assert resultado["updated"] == 1
    db.refresh(service)
    assert service.sla_late is None
    assert service.approved_value == Decimal("420.00")
    assert service.raw_status == "Solicitação Finalizada"
```

- [ ] **Step 2: Rodar os testes para confirmar que falham**

Run: `cd backend && ../.venv/Scripts/python.exe -m pytest -q tests/test_corretiva_sla_valor.py`
Expected: FAIL com `TypeError: make_linha() got an unexpected keyword argument 'sla_late'`

- [ ] **Step 3: Acrescentar os aliases**

Em `backend/app/integrations/transformar_chamados.py`, dentro de `FIELD_ALIASES`, logo após a entrada `"status"`:

```python
    "sla_late": {
        "field_ids": [620293],
        "labels": [],
    },
    "approved_value": {
        "field_ids": [613329],
        "labels": ["Valor Aprovado"],
    },
```

O label do campo 620293 é literalmente `"  "` (dois espaços). `normalizar_chave("  ")` devolve `None`, então não há entrada por label — a busca acontece pelo `field_id`. Por isso `labels` fica vazio: não há nome utilizável.

- [ ] **Step 4: Acrescentar as colunas ao modelo**

Em `backend/app/models/service.py`, trocar a linha de import do SQLAlchemy:

```python
from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
```

E acrescentar as colunas depois de `subcategory` (linha 74):

```python
    # Marca de atraso de SLA (field 620293 da Tape, devolvido como badge HTML)
    sla_late: Mapped[str | None] = mapped_column(String, nullable=True)

    # Valor aprovado do serviço (field 613329 da Tape)
    approved_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)

    # Status original da Tape, sem a normalização aplicada em `status`
    raw_status: Mapped[str | None] = mapped_column(String, nullable=True)
```

E no topo do arquivo, junto do import de `datetime`:

```python
from decimal import Decimal
```

- [ ] **Step 5: Criar a migração**

Criar `backend/migrations/versions/20261002_0003_corretiva_sla_valor.py`:

```python
"""Campos de SLA, valor aprovado e status cru para o painel de corretiva.

Revision ID: 0003
Revises: 0002
"""

from alembic import op
import sqlalchemy as sa


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("services", sa.Column("sla_late", sa.String(), nullable=True))
    op.add_column("services", sa.Column("approved_value", sa.Numeric(14, 2), nullable=True))
    op.add_column("services", sa.Column("raw_status", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("services", "raw_status")
    op.drop_column("services", "approved_value")
    op.drop_column("services", "sla_late")
```

- [ ] **Step 6: Ligar no importer**

Em `backend/app/services/importer.py`, acrescentar as três chaves ao fim da tupla `CAMPOS_SINCRONIZADOS` (depois de `"subcategory"`):

```python
    "sla_late",
    "approved_value",
    "raw_status",
```

Em `extrair_campos_negocio`, trocar o bloco que calcula o status (hoje nas linhas 384-386) por:

```python
    status_original = obter_valor_campo(
        linha, "status", obter_field_id_por_alias("status")
    )
    status = normalizar_status(status_original=status_original)
```

E acrescentar as três chaves ao fim do dicionário devolvido (depois de `"subcategory"`):

```python
        "sla_late": derivar_sla_atrasado(
            obter_valor_campo(linha, "sla_late", obter_field_id_por_alias("sla_late"))
        ),
        "approved_value": converter_decimal(
            obter_valor_campo(linha, "approved_value", obter_field_id_por_alias("approved_value"))
        ),
        "raw_status": normalizar_texto(status_original),
```

- [ ] **Step 7: Acrescentar os campos ao `make_linha`**

Em `backend/tests/conftest.py`, acrescentar dois parâmetros à assinatura de `make_linha` (depois de `non_approval_reason=None,`):

```python
    sla_late=None, approved_value=None,
```

E duas entradas ao `field_values`, depois de `"non_approval_reason"`:

```python
            "sla_late":             {"field_id": 620293, "label": "  ",                        "value": sla_late},
            "approved_value":       {"field_id": 613329, "label": "Valor Aprovado",            "value": approved_value},
```

- [ ] **Step 8: Rodar os testes para confirmar que passam**

Run: `cd backend && ../.venv/Scripts/python.exe -m pytest -q tests/test_corretiva_sla_valor.py`
Expected: PASS, 11 passed

- [ ] **Step 9: Rodar a suíte inteira**

Run: `cd backend && ../.venv/Scripts/python.exe -m pytest -q`
Expected: tudo passa, exceto a falha pré-existente de `test_migracoes.py`

- [ ] **Step 10: Commit**

```bash
git add backend/app/integrations/transformar_chamados.py backend/app/models/service.py \
        backend/app/services/importer.py backend/migrations/versions/20261002_0003_corretiva_sla_valor.py \
        backend/tests/conftest.py backend/tests/test_corretiva_sla_valor.py
git commit -m "feat(backend): persiste SLA, valor aprovado e status cru dos chamados"
```

---

## Task 3: Expor os campos em `GET /services`

**Files:**
- Modify: `backend/app/schemas/service.py`
- Modify: `backend/app/api/routes/services.py` (linhas 34-46)
- Test: `backend/tests/test_corretiva_sla_valor.py`

**Interfaces:**
- Consumes: `Service.sla_late`, `Service.approved_value`, `Service.raw_status` (Task 2)
- Produces: `ServiceItemResponse` com `sla_late: str | None`, `approved_value: float | None`, `raw_status: str | None`

- [ ] **Step 1: Escrever o teste que falha**

Acrescentar ao fim de `backend/tests/test_corretiva_sla_valor.py`:

```python
def test_services_api_expoe_campos_da_corretiva(db, upload):
    db.add(Service(
        ticket="7005",
        status="Concluído",
        raw_status="Chamado Concluído",
        praca="Natal",
        store_name="Loja Teste",
        sla_late="Atrasado",
        approved_value=Decimal("350.00"),
        upload_id=upload.id,
    ))
    db.commit()

    from app.api.routes.services import listar_servicos

    match = next(d for d in listar_servicos(db=db).dados if d.ticket == "7005")

    assert match.sla_late == "Atrasado"
    assert match.approved_value == 350.0
    assert match.raw_status == "Chamado Concluído"
```

- [ ] **Step 2: Rodar o teste para confirmar que falha**

Run: `cd backend && ../.venv/Scripts/python.exe -m pytest -q tests/test_corretiva_sla_valor.py::test_services_api_expoe_campos_da_corretiva`
Expected: FAIL com `AttributeError: 'ServiceItemResponse' object has no attribute 'sla_late'`

- [ ] **Step 3: Acrescentar ao schema**

Em `backend/app/schemas/service.py`, dentro de `ServiceItemResponse`, depois de `subcategory: str | None`:

```python
    sla_late: str | None
    approved_value: float | None
    raw_status: str | None
```

- [ ] **Step 4: Acrescentar ao mapeamento da rota**

Em `backend/app/api/routes/services.py`, dentro da construção de `ServiceItemResponse`, depois de `category=s.category, subcategory=s.subcategory,`:

```python
            sla_late=s.sla_late,
            approved_value=float(s.approved_value) if s.approved_value is not None else None,
            raw_status=s.raw_status,
```

- [ ] **Step 5: Rodar os testes para confirmar que passam**

Run: `cd backend && ../.venv/Scripts/python.exe -m pytest -q tests/test_corretiva_sla_valor.py`
Expected: PASS, 12 passed

- [ ] **Step 6: Rodar a suíte inteira**

Run: `cd backend && ../.venv/Scripts/python.exe -m pytest -q`
Expected: tudo passa, exceto a falha pré-existente de `test_migracoes.py`

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/service.py backend/app/api/routes/services.py backend/tests/test_corretiva_sla_valor.py
git commit -m "feat(backend): expõe SLA, valor aprovado e status cru em GET /services"
```

---

## Task 4: Adapter do frontend

O `adaptService` já tem uma propriedade chamada `rawStatus`, mas ela guarda o status **canônico** — nome enganoso que é exatamente a confusão que quebrou o SLA do BI. Esta task renomeia para `canonicalStatus` e libera o nome `rawStatus` para o valor que realmente é cru. O único consumidor hoje é uma asserção de teste; não há uso em produção.

**Files:**
- Modify: `frontend/src/features/indicators/dataAdapter.js` (`adaptService`, linhas 39-63)
- Modify: `frontend/src/features/indicators/indicators.test.js` (linha 41)
- Test: `frontend/src/features/indicators/indicators.test.js`

**Interfaces:**
- Consumes: payload de `GET /services` com `sla_late`, `approved_value`, `raw_status` (Task 3)
- Produces: cada registro adaptado passa a ter
  - `canonicalStatus: string` — o status canônico (antes chamado `rawStatus`)
  - `rawStatus: string` — o status cru da Tape, com fallback `'Não informado'`
  - `slaLate: boolean`
  - `approvedValue: number | null`
  - `signatureStatus: string` — texto bruto do status de assinatura, consumido pelo Total de O.S na Task 6

- [ ] **Step 1: Escrever o teste que falha**

Em `frontend/src/features/indicators/indicators.test.js`, trocar a linha 41:

```js
  assert.equal(record.rawStatus, 'Concluído')
```

por:

```js
  assert.equal(record.canonicalStatus, 'Concluído')
```

E acrescentar um teste novo ao fim do arquivo:

```js
test('adaptService expõe SLA, valor aprovado e status cru da corretiva', () => {
  const record = adaptService(service({
    status: 'Concluído',
    raw_status: 'Chamado Concluído',
    sla_late: 'Atrasado',
    approved_value: 350,
  }))

  assert.equal(record.canonicalStatus, 'Concluído')
  assert.equal(record.rawStatus, 'Chamado Concluído')
  assert.equal(record.slaLate, true)
  assert.equal(record.approvedValue, 350)
})

test('adaptService expõe o status de assinatura para o Total de O.S', () => {
  const record = adaptService(service({ signature_status: 'Concluída' }))

  assert.equal(record.signatureStatus, 'Concluída')
})

test('adaptService trata ausência dos campos da corretiva', () => {
  const record = adaptService(service({ raw_status: null, sla_late: null, approved_value: null }))

  assert.equal(record.rawStatus, 'Não informado')
  assert.equal(record.slaLate, false)
  assert.equal(record.approvedValue, null)
})

test('adaptService preserva valor aprovado zero', () => {
  const record = adaptService(service({ approved_value: 0 }))

  assert.equal(record.approvedValue, 0)
})
```

- [ ] **Step 2: Rodar o teste para confirmar que falha**

Run: `cd frontend && npm run test:indicators`
Expected: FAIL — `canonicalStatus` é `undefined` e `slaLate` não existe

- [ ] **Step 3: Implementar no adapter**

Em `frontend/src/features/indicators/dataAdapter.js`, substituir a função `adaptService` inteira por:

```js
export function adaptService(service = {}) {
  const canonicalStatus = normalizeText(service.status)
  const approvedValue = Number(service.approved_value)

  return {
    ticketId: normalizeText(service.ticket),
    status: statusDisplayLabel(canonicalStatus),
    statusGroup: classifyStatus(canonicalStatus),
    recurring: '',
    region: normalizeText(service.praca) || FALLBACK_TEXT,
    location: normalizeText(service.store_name) || FALLBACK_TEXT,
    category: normalizeText(service.category) || FALLBACK_TEXT,
    subcategory: normalizeText(service.subcategory) || FALLBACK_TEXT,
    provider: normalizeText(service.supplier) || 'Sem fornecedor',
    analyst: normalizeText(service.analyst_responsible) || FALLBACK_TEXT,
    requester: normalizeText(service.requester) || FALLBACK_TEXT,
    requestDate: normalizeApiDate(service.created_on),
    conclusionDate: normalizeApiDate(service.completion_date),
    createdOn: normalizeApiDate(service.created_on),
    inAttendanceDate: normalizeApiDate(service.in_attendance_date),
    visitDate: normalizeApiDate(service.visit_date),
    slaProgress: '',
    canonicalStatus: canonicalStatus || FALLBACK_TEXT,
    rawStatus: normalizeText(service.raw_status) || FALLBACK_TEXT,
    slaLate: normalizeText(service.sla_late).toLowerCase() === 'atrasado',
    approvedValue:
      service.approved_value === null || service.approved_value === undefined || Number.isNaN(approvedValue)
        ? null
        : approvedValue,
    signatureStatus: normalizeText(service.signature_status),
  }
}
```

`approvedValue` usa comparação explícita com `null`/`undefined` em vez de `if (!valor)`, para que **zero continue sendo zero** — são 338 registros na fotografia.

- [ ] **Step 4: Rodar o teste para confirmar que passa**

Run: `cd frontend && npm run test:indicators`
Expected: PASS, todos os testes de indicadores

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/indicators/dataAdapter.js frontend/src/features/indicators/indicators.test.js
git commit -m "feat(frontend): adapter expõe SLA, valor aprovado e status cru"
```

---

## Task 5: Filtros e contadores de status

**Files:**
- Create: `frontend/src/features/indicators/corrective/correctiveData.js`
- Create: `frontend/src/features/indicators/corrective/corrective.test.js`
- Modify: `frontend/package.json`

**Interfaces:**
- Consumes: registros do `adaptService` (Task 4), com `rawStatus`, `canonicalStatus`, `slaLate`, `approvedValue`, `createdOn`, `location`, `region`, `category`
- Produces:
  - `defaultCorrectiveFilters: { status, loja, praca, categoria, mes, ano }` — todos `'todos'`
  - `applyCorrectiveFilters(records, filters) -> records`
  - `buildFilterOptions(records) -> { status, loja, praca, categoria, mes, ano }` (listas de strings)
  - `buildStatusCounters(records) -> { emAberto, emAtendimento, naoAprovado, solicitacaoFinalizada, concluidos }`
  - `isConcluded(record) -> boolean` — a definição única de "concluído" (`canonicalStatus === "Concluído"`), usada pelas Tasks 6, 7 e 8
  - `statusPredicates: { emAberto, emAtendimento, naoAprovado, solicitacaoFinalizada, concluidos }` — um predicado por card, consumido pelos contadores e pelo drill-down da Task 8

- [ ] **Step 1: Escrever os testes que falham**

Criar `frontend/src/features/indicators/corrective/corrective.test.js`:

```js
import test from 'node:test'
import assert from 'node:assert/strict'

import {
  applyCorrectiveFilters,
  buildFilterOptions,
  buildStatusCounters,
  defaultCorrectiveFilters,
} from './correctiveData.js'

function record(overrides = {}) {
  return {
    ticketId: '1001',
    canonicalStatus: 'Concluído',
    rawStatus: 'Chamado Concluído',
    location: 'ER Centro',
    region: 'Natal',
    category: 'Elétrica',
    createdOn: '2026-09-10T08:00:00',
    slaLate: false,
    approvedValue: 100,
    signatureStatus: 'concluido',
    ...overrides,
  }
}

test('contadores de status leem o status cru, e Concluídos usa o canônico', () => {
  const counters = buildStatusCounters([
    record({ rawStatus: 'Em Aberto', canonicalStatus: 'Em Aberto' }),
    record({ rawStatus: 'Em Atendimento', canonicalStatus: 'Em atendimento' }),
    record({ rawStatus: 'Não Aprovado', canonicalStatus: 'Não Aprovado' }),
    record({ rawStatus: 'Solicitação Finalizada', canonicalStatus: 'Concluído' }),
    record({ rawStatus: 'Chamado Concluído', canonicalStatus: 'Concluído' }),
  ])

  assert.equal(counters.emAberto, 1)
  assert.equal(counters.emAtendimento, 1)
  assert.equal(counters.naoAprovado, 1)
  assert.equal(counters.solicitacaoFinalizada, 1)
  // Concluídos engloba Solicitação Finalizada: 2, não 1.
  assert.equal(counters.concluidos, 2)
})

test('status cru desconhecido entra no total e em nenhum card', () => {
  const registros = [
    record({ rawStatus: 'Status Novo Da Tape', canonicalStatus: 'Status Novo Da Tape' }),
  ]
  const counters = buildStatusCounters(registros)

  assert.equal(registros.length, 1)
  assert.equal(counters.emAberto, 0)
  assert.equal(counters.emAtendimento, 0)
  assert.equal(counters.naoAprovado, 0)
  assert.equal(counters.solicitacaoFinalizada, 0)
  assert.equal(counters.concluidos, 0)
})

test('filtros combinam loja, praça, categoria e status', () => {
  const registros = [
    record({ ticketId: 'A', location: 'ER Centro', region: 'Natal', category: 'Elétrica' }),
    record({ ticketId: 'B', location: 'ER Praia', region: 'Natal', category: 'Elétrica' }),
    record({ ticketId: 'C', location: 'ER Centro', region: 'Mossoró', category: 'Hidráulica' }),
  ]

  const porLoja = applyCorrectiveFilters(registros, { ...defaultCorrectiveFilters, loja: 'ER Centro' })
  assert.deepEqual(porLoja.map((item) => item.ticketId), ['A', 'C'])

  const porLojaEPraca = applyCorrectiveFilters(registros, {
    ...defaultCorrectiveFilters, loja: 'ER Centro', praca: 'Natal',
  })
  assert.deepEqual(porLojaEPraca.map((item) => item.ticketId), ['A'])

  const porCategoria = applyCorrectiveFilters(registros, { ...defaultCorrectiveFilters, categoria: 'Hidráulica' })
  assert.deepEqual(porCategoria.map((item) => item.ticketId), ['C'])
})

test('filtro de mês e ano usa a data de criação', () => {
  const registros = [
    record({ ticketId: 'A', createdOn: '2026-09-10T08:00:00' }),
    record({ ticketId: 'B', createdOn: '2026-10-02T08:00:00' }),
    record({ ticketId: 'C', createdOn: '2025-09-15T08:00:00' }),
  ]

  const setembro = applyCorrectiveFilters(registros, { ...defaultCorrectiveFilters, mes: '09' })
  assert.deepEqual(setembro.map((item) => item.ticketId), ['A', 'C'])

  const setembro2026 = applyCorrectiveFilters(registros, {
    ...defaultCorrectiveFilters, mes: '09', ano: '2026',
  })
  assert.deepEqual(setembro2026.map((item) => item.ticketId), ['A'])
})

test('data de criação nula não quebra o filtro nem gera opção inválida', () => {
  const registros = [
    record({ ticketId: 'A', createdOn: null }),
    record({ ticketId: 'B', createdOn: '2026-09-10T08:00:00' }),
  ]

  const opcoes = buildFilterOptions(registros)
  assert.deepEqual(opcoes.mes, ['09'])
  assert.deepEqual(opcoes.ano, ['2026'])
  assert.ok(!opcoes.mes.includes('NaN'))

  // Sem filtro de data, o registro sem data continua visível.
  assert.equal(applyCorrectiveFilters(registros, defaultCorrectiveFilters).length, 2)
  // Com filtro de data, ele sai.
  assert.deepEqual(
    applyCorrectiveFilters(registros, { ...defaultCorrectiveFilters, mes: '09' })
      .map((item) => item.ticketId),
    ['B'],
  )
})
```

- [ ] **Step 2: Rodar o teste para confirmar que falha**

Primeiro, acrescentar o script ao `frontend/package.json`, na seção `scripts`, depois de `test:indicators`:

```json
    "test:corrective": "node --test src/features/indicators/corrective/corrective.test.js",
```

Run: `cd frontend && npm run test:corrective`
Expected: FAIL — `Cannot find module './correctiveData.js'`

- [ ] **Step 3: Implementar**

Criar `frontend/src/features/indicators/corrective/correctiveData.js`:

```js
const TODOS = 'todos'

export const defaultCorrectiveFilters = {
  status: TODOS,
  loja: TODOS,
  praca: TODOS,
  categoria: TODOS,
  mes: TODOS,
  ano: TODOS,
}

function normalize(value) {
  return String(value ?? '')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .trim()
    .toLowerCase()
}

/** Devolve {ano, mes} da data de criação, ou null quando a data não existe ou é inválida. */
function dateParts(value) {
  if (!value) return null
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return null
  return {
    ano: String(parsed.getFullYear()),
    mes: String(parsed.getMonth() + 1).padStart(2, '0'),
  }
}

export function applyCorrectiveFilters(records, filters = defaultCorrectiveFilters) {
  return records.filter((record) => {
    if (filters.status !== TODOS && normalize(record.rawStatus) !== normalize(filters.status)) return false
    if (filters.loja !== TODOS && normalize(record.location) !== normalize(filters.loja)) return false
    if (filters.praca !== TODOS && normalize(record.region) !== normalize(filters.praca)) return false
    if (filters.categoria !== TODOS && normalize(record.category) !== normalize(filters.categoria)) return false

    if (filters.mes !== TODOS || filters.ano !== TODOS) {
      const parts = dateParts(record.createdOn)
      if (parts === null) return false
      if (filters.mes !== TODOS && parts.mes !== filters.mes) return false
      if (filters.ano !== TODOS && parts.ano !== filters.ano) return false
    }

    return true
  })
}

export function buildFilterOptions(records) {
  const status = new Set()
  const loja = new Set()
  const praca = new Set()
  const categoria = new Set()
  const mes = new Set()
  const ano = new Set()

  for (const record of records) {
    if (record.rawStatus) status.add(record.rawStatus)
    if (record.location) loja.add(record.location)
    if (record.region) praca.add(record.region)
    if (record.category) categoria.add(record.category)

    const parts = dateParts(record.createdOn)
    if (parts !== null) {
      mes.add(parts.mes)
      ano.add(parts.ano)
    }
  }

  const ordenar = (conjunto) => [...conjunto].sort((a, b) => a.localeCompare(b, 'pt-BR'))

  return {
    status: ordenar(status),
    loja: ordenar(loja),
    praca: ordenar(praca),
    categoria: ordenar(categoria),
    mes: [...mes].sort(),
    ano: [...ano].sort(),
  }
}

/** Verdadeiro para o conjunto de concluídos: o status canônico do chatbot-om. */
export function isConcluded(record) {
  return normalize(record.canonicalStatus) === 'concluido'
}

const cru = (record) => normalize(record.rawStatus)

/**
 * Um predicado por card de status, em um só lugar.
 *
 * Os contadores e o modal de drill-down usam exatamente estes predicados, para
 * que o número do card e a lista por trás dele nunca possam divergir.
 */
export const statusPredicates = {
  emAberto: (record) => cru(record) === 'em aberto',
  emAtendimento: (record) => cru(record) === 'em atendimento',
  naoAprovado: (record) => cru(record) === 'nao aprovado',
  solicitacaoFinalizada: (record) =>
    cru(record) === 'solicitacao finalizada' || cru(record) === 'servico finalizado',
  concluidos: isConcluded,
}

export function buildStatusCounters(records) {
  return Object.fromEntries(
    Object.entries(statusPredicates).map(([chave, predicado]) => [
      chave,
      records.filter(predicado).length,
    ]),
  )
}
```

- [ ] **Step 4: Rodar o teste para confirmar que passa**

Run: `cd frontend && npm run test:corrective`
Expected: PASS, 5 testes

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/indicators/corrective/correctiveData.js \
        frontend/src/features/indicators/corrective/corrective.test.js frontend/package.json
git commit -m "feat(frontend): filtros e contadores de status da corretiva"
```

---

## Task 6: Os quatro KPIs

**Files:**
- Modify: `frontend/src/features/indicators/corrective/correctiveData.js`
- Modify: `frontend/src/features/indicators/corrective/corrective.test.js`

**Interfaces:**
- Consumes: `isConcluded(record)` (Task 5)
- Produces: `buildCorrectiveKpis(records) -> { totalChamados, totalOs, custoMedio, sla: { percent, noPrazo, atrasado, totalConsiderado } }`

- [ ] **Step 1: Escrever os testes que falham**

Acrescentar ao fim de `frontend/src/features/indicators/corrective/corrective.test.js` (e incluir `buildCorrectiveKpis` no import do topo do arquivo):

```js
test('SLA conta só concluídos e ignora atraso em chamado não concluído', () => {
  const { sla } = buildCorrectiveKpis([
    record({ canonicalStatus: 'Concluído', slaLate: true }),
    record({ canonicalStatus: 'Concluído', slaLate: false }),
    record({ canonicalStatus: 'Concluído', slaLate: false }),
    record({ canonicalStatus: 'Concluído', slaLate: false }),
    // Atrasado, mas não concluído: fora dos dois lados da conta.
    record({ canonicalStatus: 'Não Aprovado', slaLate: true }),
    record({ canonicalStatus: 'Em atendimento', slaLate: true }),
  ])

  assert.equal(sla.atrasado, 1)
  assert.equal(sla.noPrazo, 3)
  assert.equal(sla.totalConsiderado, 4)
  assert.equal(sla.percent, 75)
})

test('custo médio divide pelos concluídos, com os sem valor entrando como zero', () => {
  const { custoMedio } = buildCorrectiveKpis([
    record({ canonicalStatus: 'Concluído', approvedValue: 300 }),
    record({ canonicalStatus: 'Concluído', approvedValue: 100 }),
    record({ canonicalStatus: 'Concluído', approvedValue: null }),
    record({ canonicalStatus: 'Concluído', approvedValue: 0 }),
    // Não concluído não entra em nenhum dos lados.
    record({ canonicalStatus: 'Em aberto', approvedValue: 900 }),
  ])

  // (300 + 100 + 0 + 0) / 4 concluídos = 100
  assert.equal(custoMedio, 100)
})

test('total de O.S conta apenas assinatura pendente ou concluída', () => {
  const { totalOs } = buildCorrectiveKpis([
    record({ signatureStatus: 'concluido' }),
    record({ signatureStatus: 'Concluída' }),
    record({ signatureStatus: 'pendente' }),
    record({ signatureStatus: 'Aguardando assinatura' }),
    record({ signatureStatus: '' }),
    record({ signatureStatus: 'cancelado' }),
  ])

  assert.equal(totalOs, 4)
})

test('base sem concluídos devolve zero em vez de dividir por zero', () => {
  const kpis = buildCorrectiveKpis([record({ canonicalStatus: 'Em aberto', approvedValue: 500 })])

  assert.equal(kpis.totalChamados, 1)
  assert.equal(kpis.custoMedio, 0)
  assert.equal(kpis.sla.percent, 0)
  assert.equal(kpis.sla.totalConsiderado, 0)
})

test('base vazia devolve tudo em zero', () => {
  const kpis = buildCorrectiveKpis([])

  assert.equal(kpis.totalChamados, 0)
  assert.equal(kpis.totalOs, 0)
  assert.equal(kpis.custoMedio, 0)
  assert.equal(kpis.sla.percent, 0)
})
```

- [ ] **Step 2: Rodar o teste para confirmar que falha**

Run: `cd frontend && npm run test:corrective`
Expected: FAIL — `buildCorrectiveKpis is not a function`

- [ ] **Step 3: Implementar**

Acrescentar ao fim de `frontend/src/features/indicators/corrective/correctiveData.js`:

```js
/** Normaliza o status de assinatura para o vocabulário do painel. */
function signatureBucket(value) {
  const texto = normalize(value)
  if (!texto) return ''
  if (texto.includes('conclu') || texto.includes('complet')) return 'concluido'
  if (texto.includes('pend') || texto.includes('aguard')) return 'pendente'
  return ''
}

export function buildCorrectiveKpis(records) {
  const concluidos = records.filter(isConcluded)

  let atrasado = 0
  for (const record of concluidos) {
    if (record.slaLate === true) atrasado += 1
  }
  const noPrazo = concluidos.length - atrasado
  const totalConsiderado = concluidos.length
  const percent = totalConsiderado === 0 ? 0 : Math.round((noPrazo / totalConsiderado) * 100)

  // Concluído sem valor aprovado entra no denominador como zero: regra do BI.
  const soma = concluidos.reduce(
    (acc, record) => acc + (typeof record.approvedValue === 'number' ? record.approvedValue : 0),
    0,
  )
  const custoMedio = concluidos.length === 0 ? 0 : Math.round(soma / concluidos.length)

  const totalOs = records.filter((record) => {
    const bucket = signatureBucket(record.signatureStatus)
    return bucket === 'pendente' || bucket === 'concluido'
  }).length

  return {
    totalChamados: records.length,
    totalOs,
    custoMedio,
    sla: { percent, noPrazo, atrasado, totalConsiderado },
  }
}
```

- [ ] **Step 4: Rodar o teste para confirmar que passa**

Run: `cd frontend && npm run test:corrective`
Expected: PASS, 10 testes

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/indicators/corrective/correctiveData.js \
        frontend/src/features/indicators/corrective/corrective.test.js
git commit -m "feat(frontend): KPIs de SLA, custo médio e O.S da corretiva"
```

---

## Task 7: Séries e rankings

**Files:**
- Modify: `frontend/src/features/indicators/corrective/correctiveData.js`
- Modify: `frontend/src/features/indicators/corrective/corrective.test.js`

**Interfaces:**
- Consumes: `isConcluded(record)` (Task 5)
- Produces:
  - `buildAnalystSeries(records, limit = 8) -> [{ label, total }]`
  - `buildMonthlySeries(records) -> [{ key, label, total, concluidos }]` ordenado por data
  - `buildRank(records, campo, limit = 8) -> [{ label, total, percent }]`

- [ ] **Step 1: Escrever os testes que falham**

Acrescentar ao fim de `corrective.test.js` (e incluir `buildAnalystSeries`, `buildMonthlySeries`, `buildRank` no import):

```js
test('ranking traz quantidade, percentual e rótulo de ausência', () => {
  const registros = [
    record({ location: 'ER Centro' }),
    record({ location: 'ER Centro' }),
    record({ location: 'ER Praia' }),
    record({ location: '' }),
  ]

  const rank = buildRank(registros, 'location')

  assert.deepEqual(rank[0], { label: 'ER Centro', total: 2, percent: 50 })
  assert.deepEqual(rank[1], { label: 'ER Praia', total: 1, percent: 25 })
  assert.equal(rank[2].label, 'Sem loja')
  assert.equal(rank[2].total, 1)
})

test('ranking respeita o limite', () => {
  const registros = Array.from({ length: 12 }, (_, indice) =>
    record({ category: `Categoria ${indice}` }),
  )

  assert.equal(buildRank(registros, 'category').length, 8)
  assert.equal(buildRank(registros, 'category', 3).length, 3)
})

test('série de analistas ordena do maior para o menor', () => {
  const series = buildAnalystSeries([
    record({ analyst: 'Ana' }),
    record({ analyst: 'Ana' }),
    record({ analyst: 'Bruno' }),
  ])

  assert.deepEqual(series, [
    { label: 'Ana', total: 2 },
    { label: 'Bruno', total: 1 },
  ])
})

test('série mensal separa concluídos do total e ordena por data', () => {
  const series = buildMonthlySeries([
    record({ createdOn: '2026-10-02T08:00:00', canonicalStatus: 'Concluído' }),
    record({ createdOn: '2026-09-10T08:00:00', canonicalStatus: 'Concluído' }),
    record({ createdOn: '2026-09-11T08:00:00', canonicalStatus: 'Em aberto' }),
    record({ createdOn: null, canonicalStatus: 'Concluído' }),
  ])

  assert.equal(series.length, 2)
  assert.equal(series[0].key, '2026-09')
  assert.equal(series[0].total, 2)
  assert.equal(series[0].concluidos, 1)
  assert.equal(series[1].key, '2026-10')
  assert.equal(series[1].total, 1)
})
```

- [ ] **Step 2: Rodar o teste para confirmar que falha**

Run: `cd frontend && npm run test:corrective`
Expected: FAIL — `buildRank is not a function`

- [ ] **Step 3: Implementar**

Acrescentar ao fim de `correctiveData.js`:

```js
const RANK_FALLBACK = {
  location: 'Sem loja',
  category: 'Sem categoria',
  region: 'Sem praça',
  analyst: 'Sem analista',
}

const MESES_PT = [
  'jan', 'fev', 'mar', 'abr', 'mai', 'jun',
  'jul', 'ago', 'set', 'out', 'nov', 'dez',
]

function contarPor(records, campo) {
  const contagem = new Map()

  for (const record of records) {
    const bruto = String(record[campo] ?? '').trim()
    const label = bruto && bruto !== 'Não informado' ? bruto : (RANK_FALLBACK[campo] ?? 'Não informado')
    contagem.set(label, (contagem.get(label) ?? 0) + 1)
  }

  return [...contagem.entries()]
    .map(([label, total]) => ({ label, total }))
    .sort((a, b) => b.total - a.total || a.label.localeCompare(b.label, 'pt-BR'))
}

export function buildRank(records, campo, limit = 8) {
  const total = records.length

  return contarPor(records, campo)
    .slice(0, limit)
    .map((item) => ({
      ...item,
      percent: total === 0 ? 0 : Math.round((item.total / total) * 100),
    }))
}

export function buildAnalystSeries(records, limit = 8) {
  return contarPor(records, 'analyst').slice(0, limit)
}

export function buildMonthlySeries(records) {
  const porMes = new Map()

  for (const record of records) {
    const parts = dateParts(record.createdOn)
    if (parts === null) continue

    const key = `${parts.ano}-${parts.mes}`
    const atual = porMes.get(key) ?? { key, label: '', total: 0, concluidos: 0 }
    atual.total += 1
    if (isConcluded(record)) atual.concluidos += 1
    atual.label = `${MESES_PT[Number(parts.mes) - 1]}/${parts.ano.slice(2)}`
    porMes.set(key, atual)
  }

  return [...porMes.values()].sort((a, b) => a.key.localeCompare(b.key))
}
```

- [ ] **Step 4: Rodar o teste para confirmar que passa**

Run: `cd frontend && npm run test:corrective`
Expected: PASS, 14 testes

- [ ] **Step 5: Rodar todos os testes do frontend**

Run: `cd frontend && npm test`
Expected: PASS em todos

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/indicators/corrective/correctiveData.js \
        frontend/src/features/indicators/corrective/corrective.test.js
git commit -m "feat(frontend): séries de analistas, mensal e rankings da corretiva"
```

---

## Task 8: Componentes do painel e encaixe na página

**Files:**
- Create: `frontend/src/features/indicators/corrective/components/CorrectiveFilters.jsx`
- Create: `frontend/src/features/indicators/corrective/components/CorrectiveKpis.jsx`
- Create: `frontend/src/features/indicators/corrective/components/CorrectiveCharts.jsx`
- Create: `frontend/src/features/indicators/corrective/components/CorrectiveRankTables.jsx`
- Create: `frontend/src/features/indicators/corrective/CorrectivePanel.jsx`
- Modify: `frontend/src/features/indicators/IndicatorsPage.jsx` (linhas 24 e 375-378)
- Modify: `frontend/src/features/indicators/indicators.css`

**Interfaces:**
- Consumes: `defaultCorrectiveFilters`, `applyCorrectiveFilters`, `buildFilterOptions`, `buildStatusCounters` (Task 5); `buildCorrectiveKpis` (Task 6); `buildAnalystSeries`, `buildMonthlySeries`, `buildRank` (Task 7)
- Produces:
  - `CorrectivePanel({ records, onOpenDetail })` — `onOpenDetail({ titulo, registros })` é opcional nesta task e ligado na Task 9
  - `CORRECTIVE_STATE_KEY = 'gentileza-indicators-corrective-v1'`

- [ ] **Step 1: Criar os filtros**

Criar `frontend/src/features/indicators/corrective/components/CorrectiveFilters.jsx`:

```jsx
const MES_LABEL = {
  '01': 'Janeiro', '02': 'Fevereiro', '03': 'Março', '04': 'Abril',
  '05': 'Maio', '06': 'Junho', '07': 'Julho', '08': 'Agosto',
  '09': 'Setembro', '10': 'Outubro', '11': 'Novembro', '12': 'Dezembro',
}

function Select({ label, value, options, onChange, mapLabel }) {
  return (
    <label className="corrective-select">
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="todos">Todos</option>
        {options.map((option) => (
          <option key={option} value={option}>
            {mapLabel ? mapLabel(option) : option}
          </option>
        ))}
      </select>
    </label>
  )
}

export default function CorrectiveFilters({ filters, options, onChange, onClear }) {
  return (
    <section className="corrective-filters" aria-label="Filtros dos chamados corretivos">
      <Select label="Status do Chamado" value={filters.status} options={options.status}
              onChange={(value) => onChange('status', value)} />
      <Select label="Loja" value={filters.loja} options={options.loja}
              onChange={(value) => onChange('loja', value)} />
      <Select label="Praça" value={filters.praca} options={options.praca}
              onChange={(value) => onChange('praca', value)} />
      <Select label="Categoria" value={filters.categoria} options={options.categoria}
              onChange={(value) => onChange('categoria', value)} />
      <Select label="Mês" value={filters.mes} options={options.mes}
              onChange={(value) => onChange('mes', value)}
              mapLabel={(value) => MES_LABEL[value] ?? value} />
      <Select label="Ano" value={filters.ano} options={options.ano}
              onChange={(value) => onChange('ano', value)} />
      <button type="button" className="corrective-filters__clear" onClick={onClear}>
        Limpar filtros
      </button>
    </section>
  )
}
```

- [ ] **Step 2: Criar os KPIs**

Criar `frontend/src/features/indicators/corrective/components/CorrectiveKpis.jsx`:

Os cinco cards de status e o Total de Chamados ficam **desabilitados** até a Task 9 ligar o modal — `onOpenDetail` chega como `undefined` nesta task. Isso é esperado, não defeito.

```jsx
import { statusPredicates } from '../correctiveData'

const MOEDA = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 })
const NUMERO = new Intl.NumberFormat('pt-BR')

function BigKpi({ title, value, subtitle, onClick }) {
  return (
    <button type="button" className="corrective-kpi" onClick={onClick} disabled={!onClick}>
      <h3>{title}</h3>
      <strong>{value}</strong>
      {subtitle ? <small>{subtitle}</small> : null}
    </button>
  )
}

function MiniKpi({ title, value, emphasis, onClick }) {
  return (
    <button
      type="button"
      className={`corrective-mini${emphasis ? ' corrective-mini--emphasis' : ''}`}
      onClick={onClick}
      disabled={!onClick}
    >
      <h4>{title}</h4>
      <strong>{NUMERO.format(value)}</strong>
    </button>
  )
}

export default function CorrectiveKpis({ kpis, counters, onOpenDetail, records }) {
  const abrir = (titulo, filtro) =>
    onOpenDetail ? () => onOpenDetail({ titulo, registros: records.filter(filtro) }) : undefined

  return (
    <>
      <section className="corrective-kpis" aria-label="Indicadores dos chamados corretivos">
        <BigKpi title="Total de Chamados" value={NUMERO.format(kpis.totalChamados)}
                onClick={abrir('Total de chamados', () => true)} />
        <BigKpi title="Total de O.S" value={NUMERO.format(kpis.totalOs)} />
        <BigKpi title="Custo Médio Serviço" value={MOEDA.format(kpis.custoMedio)} />
        <BigKpi
          title="SLA %"
          value={`${kpis.sla.percent}%`}
          subtitle={`No prazo ${NUMERO.format(kpis.sla.noPrazo)} / ${NUMERO.format(kpis.sla.totalConsiderado)} considerados`}
        />
      </section>

      <section className="corrective-status" aria-label="Chamados por status">
        <MiniKpi title="Em aberto" value={counters.emAberto}
                 onClick={abrir('Em aberto', statusPredicates.emAberto)} />
        <MiniKpi title="Em atendimento" value={counters.emAtendimento}
                 onClick={abrir('Em atendimento', statusPredicates.emAtendimento)} />
        <MiniKpi title="Não aprovado" value={counters.naoAprovado}
                 onClick={abrir('Não aprovado', statusPredicates.naoAprovado)} />
        <MiniKpi title="Solicitação Finalizada" value={counters.solicitacaoFinalizada}
                 onClick={abrir('Solicitação Finalizada', statusPredicates.solicitacaoFinalizada)} />
        <MiniKpi title="Concluídos" value={counters.concluidos} emphasis
                 onClick={abrir('Concluídos', statusPredicates.concluidos)} />
      </section>
    </>
  )
}
```

- [ ] **Step 3: Criar os gráficos**

Criar `frontend/src/features/indicators/corrective/components/CorrectiveCharts.jsx`:

```jsx
import {
  Bar, BarChart, CartesianGrid, Legend, Line, LineChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'

export default function CorrectiveCharts({ analystSeries, monthlySeries }) {
  return (
    <section className="corrective-charts">
      <article className="corrective-chart">
        <h3>Chamados por analistas</h3>
        {analystSeries.length === 0 ? (
          <p className="corrective-empty">Sem dados para o filtro atual.</p>
        ) : (
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={analystSeries}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(5,56,98,0.12)" />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} interval={0} angle={-20} textAnchor="end" height={60} />
              <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="total" name="Chamados" fill="#2f6fb3" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </article>

      <article className="corrective-chart">
        <h3>Chamados concluídos x chamados totais</h3>
        {monthlySeries.length === 0 ? (
          <p className="corrective-empty">Sem dados para o filtro atual.</p>
        ) : (
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={monthlySeries}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(5,56,98,0.12)" />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="total" name="Total" stroke="#2f6fb3" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="concluidos" name="Concluídos" stroke="#1f9d6b" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </article>
    </section>
  )
}
```

- [ ] **Step 4: Criar os rankings**

Criar `frontend/src/features/indicators/corrective/components/CorrectiveRankTables.jsx`:

```jsx
const NUMERO = new Intl.NumberFormat('pt-BR')

function RankTable({ title, columnLabel, rows }) {
  return (
    <article className="corrective-rank">
      <h3>{title}</h3>
      {rows.length === 0 ? (
        <p className="corrective-empty">Sem dados para o filtro atual.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>{columnLabel}</th>
              <th style={{ textAlign: 'right' }}>Qtd.</th>
              <th style={{ textAlign: 'right' }}>%</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.label}>
                <td>{row.label}</td>
                <td style={{ textAlign: 'right' }}>{NUMERO.format(row.total)}</td>
                <td style={{ textAlign: 'right' }}>{row.percent}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </article>
  )
}

export default function CorrectiveRankTables({ lojaRank, categoryRank }) {
  return (
    <section className="corrective-ranks">
      <RankTable title="Loja" columnLabel="Loja" rows={lojaRank} />
      <RankTable title="Categoria" columnLabel="Categoria" rows={categoryRank} />
    </section>
  )
}
```

- [ ] **Step 5: Criar o painel**

Criar `frontend/src/features/indicators/corrective/CorrectivePanel.jsx`:

```jsx
import { useMemo, useState } from 'react'
import CorrectiveFilters from './components/CorrectiveFilters'
import CorrectiveKpis from './components/CorrectiveKpis'
import CorrectiveCharts from './components/CorrectiveCharts'
import CorrectiveRankTables from './components/CorrectiveRankTables'
import {
  applyCorrectiveFilters,
  buildAnalystSeries,
  buildCorrectiveKpis,
  buildFilterOptions,
  buildMonthlySeries,
  buildRank,
  buildStatusCounters,
  defaultCorrectiveFilters,
} from './correctiveData'

export const CORRECTIVE_STATE_KEY = 'gentileza-indicators-corrective-v1'

function loadFilters() {
  try {
    const saved = sessionStorage.getItem(CORRECTIVE_STATE_KEY)
    if (!saved) return defaultCorrectiveFilters
    return { ...defaultCorrectiveFilters, ...JSON.parse(saved) }
  } catch {
    return defaultCorrectiveFilters
  }
}

function saveFilters(filters) {
  try {
    sessionStorage.setItem(CORRECTIVE_STATE_KEY, JSON.stringify(filters))
  } catch {
    // Sessão sem armazenamento disponível: os filtros valem só para esta visita.
  }
}

export default function CorrectivePanel({ records, onOpenDetail }) {
  const [filters, setFilters] = useState(loadFilters)

  const options = useMemo(() => buildFilterOptions(records), [records])
  const filtered = useMemo(() => applyCorrectiveFilters(records, filters), [records, filters])

  const kpis = useMemo(() => buildCorrectiveKpis(filtered), [filtered])
  const counters = useMemo(() => buildStatusCounters(filtered), [filtered])
  const analystSeries = useMemo(() => buildAnalystSeries(filtered), [filtered])
  const monthlySeries = useMemo(() => buildMonthlySeries(filtered), [filtered])
  const lojaRank = useMemo(() => buildRank(filtered, 'location'), [filtered])
  const categoryRank = useMemo(() => buildRank(filtered, 'category'), [filtered])

  function updateFilter(key, value) {
    const proximos = { ...filters, [key]: value }
    setFilters(proximos)
    saveFilters(proximos)
  }

  function clearFilters() {
    setFilters(defaultCorrectiveFilters)
    saveFilters(defaultCorrectiveFilters)
  }

  return (
    <div className="corrective-panel">
      <CorrectiveFilters filters={filters} options={options} onChange={updateFilter} onClear={clearFilters} />
      <CorrectiveKpis kpis={kpis} counters={counters} records={filtered} onOpenDetail={onOpenDetail} />
      <CorrectiveCharts analystSeries={analystSeries} monthlySeries={monthlySeries} />
      <CorrectiveRankTables lojaRank={lojaRank} categoryRank={categoryRank} />
    </div>
  )
}
```

- [ ] **Step 6: Encaixar na página**

Em `frontend/src/features/indicators/IndicatorsPage.jsx`, acrescentar ao bloco de imports (depois da linha 9):

```jsx
import CorrectivePanel from './corrective/CorrectivePanel'
```

E substituir o início do `dashboardBody` (hoje linhas 375-378):

```jsx
  const dashboardBody = (() => {
    if (activeIndicator !== 'performance') {
      return <IndicatorPlaceholder type={activeIndicator} />
    }
```

por:

```jsx
  const dashboardBody = (() => {
    const panelIndicators = ['performance', 'corrective']

    if (!panelIndicators.includes(activeIndicator)) {
      return <IndicatorPlaceholder type={activeIndicator} />
    }
```

E, logo depois dos guardas de `loading`, `error` e base vazia (a linha `if (records.length === 0) return <EmptyState onRetry={refresh} />`), acrescentar:

```jsx
    if (activeIndicator === 'corrective') {
      return (
        <>
          {error && (
            <div className="indicators-inline-warning" role="status">
              A última atualização falhou. Os dados carregados anteriormente continuam visíveis.
              <button type="button" onClick={refresh}>Tentar novamente</button>
            </div>
          )}
          <CorrectivePanel records={records} />
        </>
      )
    }
```

Isso faz o painel reusar os estados de carregamento, erro, base vazia e aviso de falha que já existem.

- [ ] **Step 7: Acrescentar os estilos**

Ao fim de `frontend/src/features/indicators/indicators.css`:

```css
/* Painel de chamados corretivos */
.corrective-panel { display: flex; flex-direction: column; gap: 18px; }

.corrective-filters {
  display: grid; gap: 12px; align-items: end;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  background: #fff; border: 1px solid rgba(5, 56, 98, 0.12);
  border-radius: 14px; padding: 16px;
}
.corrective-select { display: flex; flex-direction: column; gap: 6px; font-size: 12px; }
.corrective-select span { color: #5b6b7a; font-weight: 600; }
.corrective-select select {
  padding: 8px 10px; border-radius: 8px;
  border: 1px solid rgba(5, 56, 98, 0.2); background: #fff; font-size: 13px;
}
.corrective-filters__clear {
  padding: 9px 14px; border-radius: 8px; cursor: pointer;
  border: 1px solid rgba(5, 56, 98, 0.2); background: #f4f7fb;
  font-size: 13px; font-weight: 600; color: #053862;
}

.corrective-kpis, .corrective-status { display: grid; gap: 12px; }
.corrective-kpis { grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); }
.corrective-status { grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); }

.corrective-kpi, .corrective-mini {
  display: flex; flex-direction: column; gap: 6px; text-align: left;
  background: #fff; border: 1px solid rgba(5, 56, 98, 0.12);
  border-radius: 14px; padding: 16px; cursor: pointer; font: inherit;
}
.corrective-kpi:disabled, .corrective-mini:disabled { cursor: default; }
.corrective-kpi:not(:disabled):hover, .corrective-mini:not(:disabled):hover {
  border-color: rgba(5, 56, 98, 0.3);
}
.corrective-kpi h3 { margin: 0; font-size: 12px; color: #5b6b7a; text-transform: uppercase; letter-spacing: 0.04em; }
.corrective-kpi strong { font-size: 26px; color: #053862; }
.corrective-kpi small { font-size: 11px; color: #5b6b7a; }
.corrective-mini h4 { margin: 0; font-size: 12px; color: #5b6b7a; }
.corrective-mini strong { font-size: 20px; color: #053862; }
.corrective-mini--emphasis { background: #eef6ff; border-color: rgba(47, 111, 179, 0.35); }

.corrective-charts, .corrective-ranks {
  display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
}
.corrective-chart, .corrective-rank {
  background: #fff; border: 1px solid rgba(5, 56, 98, 0.12);
  border-radius: 14px; padding: 16px;
}
.corrective-chart h3, .corrective-rank h3 { margin: 0 0 12px; font-size: 14px; color: #053862; }
.corrective-rank table { width: 100%; border-collapse: collapse; font-size: 13px; }
.corrective-rank th, .corrective-rank td {
  padding: 7px 6px; border-bottom: 1px solid rgba(5, 56, 98, 0.08);
}
.corrective-rank th { color: #5b6b7a; font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; }
.corrective-empty { margin: 0; color: #5b6b7a; font-size: 13px; }

@media (max-width: 640px) {
  .corrective-filters { grid-template-columns: 1fr; }
}
```

- [ ] **Step 8: Verificar no navegador**

```bash
cd frontend && npm run dev
```

Abrir `http://localhost:5173`, ir em **Indicadores → Chamados Corretivos** e confirmar:

1. os seis filtros aparecem e respondem;
2. os quatro KPIs mostram números (SLA com o subtítulo "No prazo X / Y considerados");
3. os cinco cards de status aparecem, com Concluídos destacado;
4. os dois gráficos renderizam;
5. os dois rankings mostram quantidade e percentual;
6. voltar para **Indicador de Desempenho** e confirmar que ele continua igual;
7. mudar um filtro na corretiva, ir ao Desempenho e voltar: o filtro da corretiva foi preservado e o do Desempenho não mudou.

- [ ] **Step 9: Rodar todos os testes do frontend**

Run: `cd frontend && npm test`
Expected: PASS em todos

- [ ] **Step 10: Commit**

```bash
git add frontend/src/features/indicators/corrective/ frontend/src/features/indicators/IndicatorsPage.jsx \
        frontend/src/features/indicators/indicators.css
git commit -m "feat(frontend): painel de chamados corretivos na Central de Indicadores"
```

---

## Task 9: Modal de drill-down

Os KPIs e cards de status viram porta de entrada para a lista de chamados por trás do número.

**Files:**
- Create: `frontend/src/features/indicators/corrective/components/CorrectiveDetailModal.jsx`
- Modify: `frontend/src/features/indicators/corrective/CorrectivePanel.jsx`
- Modify: `frontend/src/features/indicators/indicators.css`

**Interfaces:**
- Consumes: `CorrectiveKpis` chama `onOpenDetail({ titulo, registros })` (Task 8)
- Produces: `CorrectiveDetailModal({ detail, onClose })`, onde `detail` é `null` ou `{ titulo, registros }`

- [ ] **Step 1: Criar o modal**

Criar `frontend/src/features/indicators/corrective/components/CorrectiveDetailModal.jsx`:

```jsx
import { useEffect } from 'react'

const NUMERO = new Intl.NumberFormat('pt-BR')
const MOEDA = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' })
const LIMITE = 200

function dataBr(value) {
  if (!value) return '—'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? '—' : parsed.toLocaleDateString('pt-BR')
}

export default function CorrectiveDetailModal({ detail, onClose }) {
  useEffect(() => {
    if (!detail) return undefined
    function onKeyDown(event) {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [detail, onClose])

  if (!detail) return null

  const { titulo, registros } = detail
  const visiveis = registros.slice(0, LIMITE)

  return (
    <div className="corrective-modal" role="dialog" aria-modal="true" aria-label={titulo}>
      <div className="corrective-modal__backdrop" onClick={onClose} />
      <div className="corrective-modal__content">
        <header>
          <div>
            <h3>{titulo}</h3>
            <p>{NUMERO.format(registros.length)} chamado(s)</p>
          </div>
          <button type="button" onClick={onClose} aria-label="Fechar">×</button>
        </header>

        {registros.length === 0 ? (
          <p className="corrective-empty">Nenhum chamado neste recorte.</p>
        ) : (
          <div className="corrective-modal__scroll">
            <table>
              <thead>
                <tr>
                  <th>Ticket</th><th>Status</th><th>Loja</th><th>Praça</th>
                  <th>Categoria</th><th>Criado em</th><th>SLA</th>
                  <th style={{ textAlign: 'right' }}>Valor</th>
                </tr>
              </thead>
              <tbody>
                {visiveis.map((record) => (
                  <tr key={record.ticketId}>
                    <td>{record.ticketId}</td>
                    <td>{record.rawStatus}</td>
                    <td>{record.location}</td>
                    <td>{record.region}</td>
                    <td>{record.category}</td>
                    <td>{dataBr(record.createdOn)}</td>
                    <td>{record.slaLate ? 'Atrasado' : 'No prazo'}</td>
                    <td style={{ textAlign: 'right' }}>
                      {typeof record.approvedValue === 'number' ? MOEDA.format(record.approvedValue) : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {registros.length > LIMITE && (
          <footer>
            Mostrando os primeiros {NUMERO.format(LIMITE)} de {NUMERO.format(registros.length)}. Use os filtros para estreitar.
          </footer>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Ligar no painel**

Em `frontend/src/features/indicators/corrective/CorrectivePanel.jsx`, acrescentar o import:

```jsx
import CorrectiveDetailModal from './components/CorrectiveDetailModal'
```

Acrescentar o estado, depois da linha `const [filters, setFilters] = useState(loadFilters)`:

```jsx
  const [detail, setDetail] = useState(null)
```

Trocar a linha do `CorrectiveKpis` para usar o estado local em vez da prop:

```jsx
      <CorrectiveKpis kpis={kpis} counters={counters} records={filtered} onOpenDetail={setDetail} />
```

E acrescentar o modal antes do fechamento da `div`:

```jsx
      <CorrectiveDetailModal detail={detail} onClose={() => setDetail(null)} />
```

A prop `onOpenDetail` do `CorrectivePanel` deixa de ser usada; remova-a da assinatura:

```jsx
export default function CorrectivePanel({ records }) {
```

- [ ] **Step 3: Acrescentar os estilos do modal**

Ao fim de `frontend/src/features/indicators/indicators.css`:

```css
/* Modal de detalhe da corretiva */
.corrective-modal { position: fixed; inset: 0; z-index: 60; display: grid; place-items: center; padding: 20px; }
.corrective-modal__backdrop { position: absolute; inset: 0; background: rgba(5, 25, 45, 0.5); }
.corrective-modal__content {
  position: relative; display: flex; flex-direction: column; gap: 12px;
  width: min(1040px, 100%); max-height: 84vh; padding: 20px;
  background: #fff; border-radius: 16px; box-shadow: 0 24px 60px rgba(5, 25, 45, 0.3);
}
.corrective-modal__content header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.corrective-modal__content header h3 { margin: 0; font-size: 16px; color: #053862; }
.corrective-modal__content header p { margin: 4px 0 0; font-size: 12px; color: #5b6b7a; }
.corrective-modal__content header button {
  border: none; background: transparent; cursor: pointer;
  font-size: 24px; line-height: 1; color: #5b6b7a;
}
.corrective-modal__scroll { overflow: auto; }
.corrective-modal__scroll table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
.corrective-modal__scroll th, .corrective-modal__scroll td {
  padding: 7px 8px; border-bottom: 1px solid rgba(5, 56, 98, 0.08); white-space: nowrap;
}
.corrective-modal__scroll th {
  position: sticky; top: 0; background: #f4f7fb; color: #5b6b7a;
  font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em;
}
.corrective-modal__content footer { font-size: 12px; color: #5b6b7a; }
```

- [ ] **Step 4: Verificar no navegador**

```bash
cd frontend && npm run dev
```

Em **Indicadores → Chamados Corretivos**:

1. clicar em **Total de Chamados** abre o modal com a contagem e a tabela;
2. a coluna SLA mostra "Atrasado" ou "No prazo";
3. a coluna Valor mostra moeda, e `—` quando não há valor;
4. `Esc` e o clique fora fecham o modal;
5. os cinco cards de status abrem o modal, e a contagem no cabeçalho do modal é **igual** ao número do card — eles usam o mesmo predicado;
6. com um filtro ativo, o modal respeita o filtro.

- [ ] **Step 5: Rodar todos os testes do frontend**

Run: `cd frontend && npm test`
Expected: PASS em todos

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/indicators/corrective/ frontend/src/features/indicators/indicators.css
git commit -m "feat(frontend): drill-down dos KPIs da corretiva"
```

---

## Task 10: Validação ao vivo e documentação

Os campos novos só existem para registros sincronizados **depois** da Task 2. Esta task roda a sincronização, confere os números contra a fotografia e documenta a diferença.

**Files:**
- Create: `docs/integracao-bi-corretiva.md`
- Reference: `Manutenções Corretivas - All data (29).xlsx` (fotografia, 4.899 linhas)

**Interfaces:**
- Consumes: tudo das Tasks 1-9

- [ ] **Step 1: Aplicar a migração e subir o backend atualizado**

```bash
docker cp backend/app chatbot-backend:/app/app
docker cp backend/migrations chatbot-backend:/app/migrations
docker restart chatbot-backend
```

Confirmar que a migração chegou ao head:

```bash
docker exec chatbot-backend python -c "from app.db.migrations import versao; from app.db.session import engine; print(versao(engine))"
```

Expected: `0003`

- [ ] **Step 2: Sincronizar a Tape**

```bash
docker exec chatbot-backend python -c "from app.tasks.tape_scheduler import executar_sincronizacao_tape; executar_sincronizacao_tape()"
```

Expected: termina sem erro. A sincronização é paginada e pode levar vários minutos.

- [ ] **Step 3: Conferir os números no banco**

```bash
docker exec chat-bot-om-db-1 sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
select count(*) filter (where status = '"'"'Concluído'"'"') as concluidos,
       count(*) filter (where status = '"'"'Concluído'"'"' and sla_late = '"'"'Atrasado'"'"') as atrasados,
       count(*) filter (where status = '"'"'Concluído'"'"' and approved_value is not null) as com_valor,
       round(sum(approved_value) filter (where status = '"'"'Concluído'"'"')) as soma_valor,
       count(distinct raw_status) as status_crus
from services;
"'
```

Expected, comparado à fotografia (4.899 linhas; a base tem ~4.894 pela regra de praça):
- `concluidos` próximo de 3.779
- `atrasados` próximo de 678
- `com_valor` próximo de 2.672
- `soma_valor` próximo de 751.895
- `status_crus` igual a 6 (`Chamado Concluído`, `Não Aprovado`, `Solicitação Finalizada`, `Em Atendimento`, `Em Aberto`, `Pendente de Aprovação`)

Se `atrasados` vier **zero**, a derivação do HTML falhou: confirme que `derivar_sla_atrasado` está removendo as tags antes de procurar "atrasado".

- [ ] **Step 4: Conferir o painel no navegador**

Abrir `http://localhost:5173` → **Indicadores → Chamados Corretivos** e comparar com os alvos: SLA próximo de **82%**, custo médio próximo de **R$ 199**, Total de O.S próximo de **2.285**, Concluídos próximo de **3.779** e Solicitação Finalizada próximo de **600**.

- [ ] **Step 5: Escrever a documentação**

Criar `docs/integracao-bi-corretiva.md`:

```markdown
# Painel de Chamados Corretivos

Ciclo 1 do merge do `bi-manutencao` no chatbot-om. Spec:
`docs/superpowers/specs/2026-10-02-bi-manutencao-corretiva-design.md`.

## Arquitetura

O painel não tem endpoint próprio, tabela de cache nem upload de planilha. Ele
consome os registros que a `IndicatorsPage` já carrega de `GET /services`.

```text
Tape API (app 57531)
  → FIELD_ALIASES: sla_late (620293), approved_value (613329)
  → TapeTransformer → importer → Service → GET /services
  → dataAdapter → features/indicators/corrective/
```

## Campos acrescentados

| Campo | Origem | Observação |
|---|---|---|
| `sla_late` | field 620293 | A Tape devolve **badge HTML**, não texto. A derivação procura "atrasado" dentro do HTML |
| `approved_value` | field 613329 | Zero é valor válido, não ausência |
| `raw_status` | field 580453 | Status original; `status` continua normalizado |

O `raw_status` **não** tem alias próprio: o `FIELD_ALIAS_INDEX` mapeia
`field_id → alias` um-para-um, e declarar o campo 580453 duas vezes faria um dos
dois desaparecer. Ele é derivado do mesmo alias `status`, antes da normalização.

## Regras de cálculo

- **Concluído** (SLA, custo médio, card Concluídos): `status == "Concluído"`, que
  engloba `Chamado Concluído` e `Solicitação Finalizada`.
- **SLA %** = no prazo / concluídos. Chamado não concluído fica fora dos dois
  lados, mesmo marcado como atrasado.
- **Custo médio** = soma dos valores dos concluídos ÷ **todos** os concluídos.
  Concluído sem valor entra no denominador como zero.
- **Total de O.S** = assinatura pendente ou concluída.
- Os cards de status **não somam** o Total de Chamados: Concluídos engloba
  Solicitação Finalizada, e `Pendente de Aprovação` não tem card — o painel de
  origem também não mostra esse status.

## O bug de SLA do BI Manutenção

O `ChamadoTransformer` do `bi-manutencao` chama o campo de `coluna_d_raw`
(coluna D, a marca de atraso), mas o alias dele aponta para
`["progresso do sla", "progresso sla"]` — outra coluna, cujo texto satura em 100%
e nunca diz "atrasado". Por isso o SLA do BI classifica **todos** os concluídos
como no prazo. Este painel lê o campo correto.

## Validação contra a fotografia

Planilha `Manutenções Corretivas - All data (29).xlsx`, 4.899 linhas.

| Medida | Fotografia |
|---|---|
| Concluídos | 3.779 |
| Atrasados entre concluídos | 678 |
| SLA % | 82% |
| Concluídos com valor aprovado | 2.672 (soma R$ 751.895,03) |
| Custo médio | R$ 199 |
| Total de O.S | 2.285 |
| Solicitação Finalizada | 600 |

A base tem ~4.894 registros porque a regra de praça do importer descarta
registros sem praça ou com praça "Escritório". A diferença é deliberada e não
foi corrigida para forçar igualdade com a planilha.

## Fora deste ciclo

Preventiva e Financeiro; trocar a regra de SLA por `prazo` vs
`diasUteisPassados` (a fotografia tem 2.130 registros acima do prazo contra 678
marcados como atrasados — os critérios discordam); remover o normalizador de
status; novas permissões.
```

- [ ] **Step 6: Rodar as duas suítes**

```bash
cd backend && ../.venv/Scripts/python.exe -m pytest -q
cd ../frontend && npm test
```

Expected: tudo passa, exceto a falha pré-existente de `test_migracoes.py`

- [ ] **Step 7: Commit**

```bash
git add docs/integracao-bi-corretiva.md
git commit -m "docs: validação do painel de chamados corretivos"
```
