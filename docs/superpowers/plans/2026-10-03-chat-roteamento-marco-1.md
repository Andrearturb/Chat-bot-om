# Roteamento do Chat — Marco 1: a espinha

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Substituir o roteador de regex achatado por um roteador de dois eixos testado, unificar o estado conversacional no `dataTable` do n8n, e passar a autorizar por domínio — sem adicionar nenhum domínio novo.

**Architecture:** O roteador deixa de ser string inline no script de patch e passa a ser um módulo JS puro no repositório, com testes. O nó `Buscar Estado da Conversa` vira o primeiro do fluxo, para o roteador ler `domain` do próprio `dataTable` em vez de depender do backend. O comprovante HMAC passa a carregar os domínios permitidos. O backend deixa de carregar estado de consulta.

**Tech Stack:** n8n 2.39.5 (SQLite em `/home/node/.n8n/database.sqlite`), Node 24 (via container `chatbot-frontend`), FastAPI + SQLAlchemy + Alembic, pytest, `node --test`.

**Spec:** [docs/superpowers/specs/2026-10-03-chat-roteamento-quatro-dominios-design.md](../specs/2026-10-03-chat-roteamento-quatro-dominios-design.md)

## Global Constraints

- Domínios válidos, exatamente estas strings: `chamados_corretiva`, `chamados_preventiva`, `ativos`, `custos`. Mais `desconhecido` e `sem_acesso` como resultados do roteador.
- Contas razão: corretiva `41140014`, preventiva `41140026`.
- O prompt de 85 KB do nó `Interpretar Estado da Consulta` **não é alterado** neste marco.
- Nenhum domínio novo entra neste marco. Perguntas de preventiva e custos devem cair em `desconhecido`.
- Nenhum SQL vem do modelo de IA.
- Permissões por domínio: `ativos` exige `assets.view`; `chamados_corretiva`, `chamados_preventiva` e `custos` exigem `indicators.view`.
- Comprovante HMAC válido por 180 segundos, assinado com `INTERNAL_API_KEY`.
- Testes de backend: `cd backend && ../.venv/Scripts/python.exe -m pytest -q`. O container `chatbot-backend` **não** tem pytest.
- Testes de frontend e do roteador: `docker exec chatbot-frontend npm test`.
- `docker cp` de diretório precisa do sufixo `/.` para sobrescrever em vez de aninhar.
- Comandos `docker exec` com caminho absoluto Unix precisam de `MSYS_NO_PATHCONV=1` no Git Bash.
- Backup já feito: `n8n/workflows/backup-2026-10-03-*.json` (commit `8a65abe`) e `scratchpad/n8n-backup/`.

## Review Focus

1. **`domain` nulo nas 117 linhas existentes** — a tabela `chat_query_state` já tem 117 linhas e nenhuma terá `domain` preenchido depois de a coluna ser criada. O roteador deve tratar `null`/`undefined`/string vazia como "sem contexto anterior" e cair em `desconhecido`, nunca lançar. Teste na Tarefa 1.
2. **`allowedDomains` vazio** — usuário sem `assets.view` nem `indicators.view`. Toda pergunta reconhecida deve virar `sem_acesso` nomeando o domínio negado, não `desconhecido`. Teste na Tarefa 1.
3. **Mensagem vazia, nula ou só pontuação** — `chatInput` vazio não pode lançar nem casar regex por acidente; deve dar `desconhecido` (ou o `lastDomain`, se houver). Teste na Tarefa 1.
4. **Qualificadores contraditórios na mesma frase** — "chamados corretivos e preventivos" deve resolver de forma determinística e documentada (preventivo vence, por ser testado primeiro), não depender de ordem de regex acidental. Teste na Tarefa 1.
5. **`lastDomain` com valor que não é domínio válido** — estado antigo ou corrompido com `domain` = `"service"` (o nome usado pelo roteador antigo) não pode virar domínio. Deve ser descartado e cair em `desconhecido`. Teste na Tarefa 1.

---

## Estrutura de arquivos

**Criar:**
- `n8n/router/route.js` — lógica pura do roteador, única fonte da verdade
- `n8n/router/route.test.js` — testes do roteador em `node --test`
- `backend/tests/test_query_access.py` — autorização por domínio
- `backend/migrations/versions/20261003_0008_drop_asset_query_state.py`

**Modificar:**
- `n8n/add_asset_query_branch.py` — ler o roteador do `.js`; reposicionar `Buscar Estado`; salvar `domain`; generalizar o nó de acesso negado; remover o Gemini duplicado
- `backend/app/services/asset_query_access.py` — comprovante com `domains`
- `backend/app/api/routes/chatbot.py` — commitar o endpoint e aplicar o gate de domínio
- `backend/app/api/routes/assistant.py` — emitir `domains`; parar de carregar estado
- `backend/app/models/auth.py` — remover `asset_query_state`
- `docker-compose.yml` — montar `./n8n` no container do frontend
- `frontend/package.json` — registrar o teste do roteador
- `docs/integracao-ativos-chat.md` — atualizar o contrato documentado

---

### Task 1: Módulo do roteador com testes

É o coração do marco. Lógica pura, sem nada do n8n, para poder ser testada.

**Files:**
- Create: `n8n/router/route.js`
- Create: `n8n/router/route.test.js`
- Modify: `docker-compose.yml` (serviço `frontend`, bloco `volumes`)
- Modify: `frontend/package.json` (script `test`)

**Interfaces:**
- Consumes: nada.
- Produces: `n8n/router/route.js` exportando:
  - `route({ chatInput, lastDomain, allowedDomains })` → `{ domain, contaRazao, deniedDomain }`, onde `domain` é um de `chamados_corretiva` | `chamados_preventiva` | `ativos` | `custos` | `desconhecido` | `sem_acesso`; `contaRazao` é `'41140014'` | `'41140026'` | `null`; `deniedDomain` é o domínio pretendido quando `domain === 'sem_acesso'`, senão `null`.
  - `preservarEstado(estadoAnterior, dominioNovo)` → objeto com o estado que sobrevive ao turno: tudo, se o domínio não mudou; só os campos compartilhados, se mudou.
  - `DOMINIOS_VALIDOS` (Set), `CAMPOS_COMPARTILHADOS` (Set) e `normalizar(valor)`.

- [ ] **Step 1: Montar `./n8n` no container do frontend**

O container do frontend monta só `./frontend:/app`, então `n8n/router/` não é visível lá. Em `docker-compose.yml`, no serviço `frontend`, acrescentar a terceira linha de volume:

```yaml
    volumes:
      - ./frontend:/app
      - frontend_node_modules:/app/node_modules
      # Testes do roteador do n8n rodam no Node deste container; o repositório
      # não tem Node instalado no host.
      - ./n8n:/n8n:ro
```

- [ ] **Step 2: Recriar o container para aplicar o volume**

Run: `docker compose up -d --no-deps frontend`
Expected: o container `chatbot-frontend` é recriado.

Run: `MSYS_NO_PATHCONV=1 docker exec chatbot-frontend ls /n8n/add_asset_query_branch.py`
Expected: `/n8n/add_asset_query_branch.py`

- [ ] **Step 3: Escrever o teste do roteador, que falha**

Create `n8n/router/route.test.js`:

```js
'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');

const { route, preservarEstado, normalizar, DOMINIOS_VALIDOS } = require('./route.js');

const TODOS = ['chamados_corretiva', 'chamados_preventiva', 'ativos', 'custos'];

const rotear = (chatInput, extra = {}) =>
  route({ chatInput, lastDomain: null, allowedDomains: TODOS, ...extra });

test('custo vence ativo e o qualificador vira filtro de conta razão', () => {
  assert.equal(rotear('quanto gastamos com ar condicionado').domain, 'custos');
  const corretiva = rotear('qual o custo de manutenção corretiva em agosto?');
  assert.equal(corretiva.domain, 'custos');
  assert.equal(corretiva.contaRazao, '41140014');
  const preventiva = rotear('custo de manutenção preventiva');
  assert.equal(preventiva.domain, 'custos');
  assert.equal(preventiva.contaRazao, '41140026');
  assert.equal(rotear('qual loja teve o maior custo de manutenção?').contaRazao, null);
});

test('chamado vence ativo', () => {
  // Pergunta de chamado filtrada por categoria, não consulta de inventário.
  assert.equal(rotear('quantos chamados de ar condicionado?').domain, 'chamados_corretiva');
  assert.equal(rotear('quantos chamados estão abertos?').domain, 'chamados_corretiva');
});

test('qualificador decide o subtipo do chamado', () => {
  assert.equal(rotear('quantos chamados preventivos foram concluídos?').domain, 'chamados_preventiva');
  assert.equal(rotear('quantos chamados corretivos?').domain, 'chamados_corretiva');
});

test('qualificador sozinho implica chamado e vence marcador de ativo', () => {
  assert.equal(rotear('liste as preventivas atrasadas da praça Natal').domain, 'chamados_preventiva');
  // Tem "climatizacao" (ativo) e "preventivas" (qualificador): é chamado preventivo.
  assert.equal(rotear('qual a periodicidade das preventivas de climatização?').domain, 'chamados_preventiva');
});

test('ativo sem outro marcador vai para o inventário', () => {
  assert.equal(rotear('quantos extintores existem na loja 4006?').domain, 'ativos');
  assert.equal(rotear('liste os purificadores da praça Natal').domain, 'ativos');
});

test('sem marcador usa o domínio anterior', () => {
  assert.equal(rotear('e na praça Natal?', { lastDomain: 'ativos' }).domain, 'ativos');
  assert.equal(rotear('e quantos desses tem na loja 4006?', { lastDomain: 'custos' }).domain, 'custos');
});

test('sem marcador e sem contexto é desconhecido', () => {
  assert.equal(rotear('qual a capital da França?').domain, 'desconhecido');
});

test('acento e caixa não alteram a rota', () => {
  assert.equal(rotear('QUANTOS CHAMADOS PREVENTIVOS?').domain, 'chamados_preventiva');
  assert.equal(rotear('quantos chamados preventivos?').domain, 'chamados_preventiva');
  assert.equal(normalizar('Climatização'), 'climatizacao');
});

// --- Review Focus ---

test('domain nulo das 117 linhas existentes não vira domínio', () => {
  // A coluna domain será criada depois das linhas; todas vêm nulas.
  for (const vazio of [null, undefined, '', '   ']) {
    assert.equal(rotear('e na praça Natal?', { lastDomain: vazio }).domain, 'desconhecido');
  }
});

test('lastDomain inválido é descartado', () => {
  // "service" era o nome do roteador antigo e não é domínio válido.
  for (const invalido of ['service', 'asset', 'chamados', 'qualquer_coisa']) {
    assert.equal(rotear('e na praça Natal?', { lastDomain: invalido }).domain, 'desconhecido');
  }
});

test('sem permissão o domínio reconhecido vira sem_acesso, não desconhecido', () => {
  const negado = rotear('quantos extintores na loja 4006?', { allowedDomains: [] });
  assert.equal(negado.domain, 'sem_acesso');
  assert.equal(negado.deniedDomain, 'ativos');

  const soAtivos = rotear('quantos chamados abertos?', { allowedDomains: ['ativos'] });
  assert.equal(soAtivos.domain, 'sem_acesso');
  assert.equal(soAtivos.deniedDomain, 'chamados_corretiva');

  // Desconhecido não é negado: não há domínio a negar.
  assert.equal(rotear('qual a capital da França?', { allowedDomains: [] }).domain, 'desconhecido');
});

test('mensagem vazia, nula ou só pontuação não lança', () => {
  for (const vazio of [null, undefined, '', '   ', '???', '...']) {
    assert.equal(rotear(vazio).domain, 'desconhecido');
    assert.equal(rotear(vazio, { lastDomain: 'ativos' }).domain, 'ativos');
  }
});

test('qualificadores contraditórios resolvem de forma determinística', () => {
  // Preventivo é testado primeiro, então vence. Regra documentada, não acidente.
  assert.equal(rotear('chamados corretivos e preventivos').domain, 'chamados_preventiva');
});

test('DOMINIOS_VALIDOS não inclui os resultados de controle', () => {
  assert.equal(DOMINIOS_VALIDOS.has('ativos'), true);
  assert.equal(DOMINIOS_VALIDOS.has('desconhecido'), false);
  assert.equal(DOMINIOS_VALIDOS.has('sem_acesso'), false);
});

// --- preservação de estado na troca de domínio ---

test('mesmo domínio preserva o estado inteiro', () => {
  const anterior = {
    domain: 'chamados_corretiva', praca: 'Natal', supplier: 'ONFLY',
    category: 'Climatização', year: 2026,
  };
  const mantido = preservarEstado(anterior, 'chamados_corretiva');

  assert.equal(mantido.praca, 'Natal');
  assert.equal(mantido.supplier, 'ONFLY');
  assert.equal(mantido.category, 'Climatização');
  assert.equal(mantido.year, 2026);
});

test('trocar de domínio preserva só os campos compartilhados', () => {
  const anterior = {
    domain: 'chamados_corretiva', praca: 'Natal', year: 2026, month: 8,
    supplier: 'ONFLY', category: 'Climatização', status: 'Concluído',
    analyst_responsible: 'Ana', selection_context: '{"lojas":["x"]}',
  };
  const mantido = preservarEstado(anterior, 'ativos');

  // Compartilhados sobrevivem: "e na praça Natal?" continua funcionando.
  assert.equal(mantido.praca, 'Natal');
  assert.equal(mantido.year, 2026);
  assert.equal(mantido.month, 8);
  // Específicos do domínio anterior não contaminam o novo.
  for (const vazou of ['supplier', 'category', 'status', 'analyst_responsible', 'selection_context']) {
    assert.equal(mantido[vazou], undefined, `${vazou} vazou para o domínio novo`);
  }
});

test('conta_razao de custos não vaza para ativos', () => {
  const anterior = { domain: 'custos', conta_razao: '41140014', praca: 'Natal' };
  const mantido = preservarEstado(anterior, 'ativos');

  assert.equal(mantido.conta_razao, undefined);
  assert.equal(mantido.praca, 'Natal');
});

test('estado anterior ausente ou sem domínio não lança', () => {
  for (const vazio of [null, undefined, {}]) {
    const mantido = preservarEstado(vazio, 'ativos');
    assert.equal(typeof mantido, 'object');
    assert.equal(mantido.praca, undefined);
  }
});

test('as 117 linhas sem domain são tratadas como troca de domínio', () => {
  // domain nulo: não há como saber de que domínio o estado é, então só o
  // compartilhado sobrevive.
  const anterior = { domain: null, praca: 'Natal', supplier: 'ONFLY' };
  const mantido = preservarEstado(anterior, 'ativos');

  assert.equal(mantido.praca, 'Natal');
  assert.equal(mantido.supplier, undefined);
});
```

- [ ] **Step 4: Rodar o teste e confirmar que falha**

Run: `MSYS_NO_PATHCONV=1 docker exec chatbot-frontend node --test /n8n/router/`
Expected: FAIL — `Cannot find module './route.js'`

- [ ] **Step 5: Escrever o módulo do roteador**

Create `n8n/router/route.js`:

```js
'use strict';

// Fonte única do roteador. O nó "Roteamento da Consulta" do n8n é artefato
// gerado: add_asset_query_branch.py injeta este arquivo e acrescenta o invólucro
// que lê $input e devolve [{ json }]. Editar o nó na interface do n8n faz o
// teste de contrato falhar — edite aqui.

const ENTIDADES = {
  custo: /\b(custos?|gastos?|gastamos|gastou|gastar|despesas?)\b/,
  chamado: /\b(chamados?|tickets?|ordens? de servico|solicitacoes?|atendimentos?)\b/,
  ativo: /\b(ativos?|equipamentos?|inventario|climatizacao|climatizadores?|ar(?:es)?[ -]?condicionad[oa]s?|maquinas? de ar|splits?|extintores?|incendio|purificadores?|gelagua|bebedouros?|filtros? de agua|btus?)\b/,
};

const QUALIFICADORES = {
  preventivo: /\b(preventivas?|preventivos?)\b/,
  corretivo: /\b(corretivas?|corretivos?)\b/,
};

const CONTA_RAZAO = { corretivo: '41140014', preventivo: '41140026' };

const DOMINIOS_VALIDOS = new Set([
  'chamados_corretiva', 'chamados_preventiva', 'ativos', 'custos',
]);

// Dimensões que fazem sentido nos quatro domínios e por isso sobrevivem à troca
// de assunto: é o que mantém "e na praça Natal?" funcionando. Tudo que não está
// aqui é específico de um domínio e é descartado ao trocar, para que um
// fornecedor de chamado não contamine um ranking de custo.
const CAMPOS_COMPARTILHADOS = new Set([
  'praca', 'store_name', 'start_date', 'end_date', 'year', 'month',
  'date_field', 'group_by', 'limit', 'list_limit', 'sort_by', 'sort_order',
  'query_shape', 'response_format',
]);

function normalizar(valor) {
  return String(valor == null ? '' : valor)
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase();
}

function detectar(texto) {
  const v = normalizar(texto);
  // Precedência de entidade: custo, chamado, ativo. "Chamados de ar
  // condicionado" é chamado filtrado por categoria, não inventário.
  const entidade = ENTIDADES.custo.test(v) ? 'custo'
    : ENTIDADES.chamado.test(v) ? 'chamado'
    : ENTIDADES.ativo.test(v) ? 'ativo'
    : null;
  const qualificador = QUALIFICADORES.preventivo.test(v) ? 'preventivo'
    : QUALIFICADORES.corretivo.test(v) ? 'corretivo'
    : null;
  return { entidade, qualificador };
}

function dominioDeChamado(qualificador) {
  return qualificador === 'preventivo' ? 'chamados_preventiva' : 'chamados_corretiva';
}

function route({ chatInput, lastDomain, allowedDomains } = {}) {
  const { entidade, qualificador } = detectar(chatInput);
  const anterior = typeof lastDomain === 'string' && DOMINIOS_VALIDOS.has(lastDomain.trim())
    ? lastDomain.trim()
    : null;

  let dominio = null;
  let contaRazao = null;

  if (entidade === 'custo') {
    dominio = 'custos';
    contaRazao = qualificador ? CONTA_RAZAO[qualificador] : null;
  } else if (entidade === 'chamado' || qualificador) {
    dominio = dominioDeChamado(qualificador);
  } else if (entidade === 'ativo') {
    dominio = 'ativos';
  } else if (anterior) {
    dominio = anterior;
  }

  if (!dominio) return { domain: 'desconhecido', contaRazao: null, deniedDomain: null };

  const permitidos = Array.isArray(allowedDomains) ? allowedDomains : [];
  if (!permitidos.includes(dominio)) {
    return { domain: 'sem_acesso', contaRazao: null, deniedDomain: dominio };
  }
  return { domain: dominio, contaRazao, deniedDomain: null };
}

function preservarEstado(estadoAnterior, dominioNovo) {
  const anterior = estadoAnterior && typeof estadoAnterior === 'object' ? estadoAnterior : {};
  const dominioAnterior = typeof anterior.domain === 'string' ? anterior.domain.trim() : '';
  if (dominioAnterior && dominioAnterior === dominioNovo) return { ...anterior };
  // Domínio mudou, ou o estado é antigo e não registra domínio: só o
  // compartilhado atravessa.
  const mantido = {};
  for (const campo of CAMPOS_COMPARTILHADOS) {
    if (anterior[campo] !== undefined && anterior[campo] !== null) mantido[campo] = anterior[campo];
  }
  return mantido;
}

// --- fim da lógica pura; nada abaixo desta linha é injetado no n8n ---
module.exports = {
  route, preservarEstado, detectar, normalizar,
  DOMINIOS_VALIDOS, CAMPOS_COMPARTILHADOS, CONTA_RAZAO,
};
```

- [ ] **Step 6: Rodar o teste e confirmar que passa**

Run: `MSYS_NO_PATHCONV=1 docker exec chatbot-frontend node --test /n8n/router/`
Expected: PASS, 19 testes.

- [ ] **Step 7: Registrar o teste do roteador no `npm test`**

Em `frontend/package.json`, acrescentar o script dedicado e incluir o **diretório** no `test` — diretório, e não arquivo, para que o teste de contrato da Tarefa 2 entre sozinho. O caminho `/n8n/router/` é absoluto no container:

```json
    "test:router": "node --test /n8n/router/",
    "test": "node --test src/lib/apiClient.test.js src/lib/conversations.test.js src/features/auth/authErrors.test.js src/features/audit/audit.test.js src/features/indicators/indicators.test.js src/features/indicators/corrective/corrective.test.js src/features/indicators/preventive/preventive.test.js src/features/indicators/costs/costs.test.js src/features/assets/assets.test.js src/features/assets/filters.test.js /n8n/router/"
```

- [ ] **Step 8: Rodar a suíte inteira do frontend**

Run: `docker exec chatbot-frontend npm test`
Expected: PASS — 74 testes anteriores mais 19 do roteador, 93 no total, 0 falhas.

- [ ] **Step 9: Commit**

```bash
git add n8n/router/route.js n8n/router/route.test.js docker-compose.yml frontend/package.json
git commit -m "feat(n8n): roteador de dois eixos como modulo testado

O roteador deixa de ser string inline no script de patch e passa a ser
modulo JS puro com 19 testes, incluindo os cinco casos de borda que o
spec implica: domain nulo das 117 linhas existentes, lastDomain
invalido, allowedDomains vazio, mensagem vazia e qualificadores
contraditorios.

preservarEstado implementa a regra de troca de dominio do spec: mesmo
dominio preserva tudo, dominio diferente preserva so as dimensoes
compartilhadas, para que praca e periodo atravessem a troca de assunto
mas fornecedor e conta_razao nao contaminem o dominio seguinte.

Precedencia: custo, chamado, qualificador sozinho, ativo, lastDomain,
desconhecido. Chamado vence ativo para que 'chamados de ar
condicionado' nao caia no inventario.

O container do frontend passa a montar ./n8n em modo leitura, porque o
host nao tem Node e os testes rodam no Node 24 de lá."
```

---

### Task 2: O injetor lê o roteador do arquivo

**Files:**
- Modify: `n8n/add_asset_query_branch.py:15-48` (remover `ROUTER_CODE` inline), `:202-215`, `:245`
- Create: teste de contrato em `n8n/router/contrato.test.js`

**Interfaces:**
- Consumes: `n8n/router/route.js` da Tarefa 1, incluindo o marcador de fim da lógica pura.
- Produces: função `router_code()` em `add_asset_query_branch.py`, devolvendo o `jsCode` completo do nó.

- [ ] **Step 1: Escrever o teste de contrato, que falha**

Create `n8n/router/contrato.test.js`:

```js
'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const MARCADOR = '// --- fim da lógica pura; nada abaixo desta linha é injetado no n8n ---';

test('route.js tem o marcador que o injetor usa para cortar', () => {
  const fonte = fs.readFileSync(path.join(__dirname, 'route.js'), 'utf8');
  assert.equal(fonte.includes(MARCADOR), true,
    'sem o marcador, add_asset_query_branch.py nao sabe onde cortar o module.exports');
  assert.equal(fonte.indexOf(MARCADOR), fonte.lastIndexOf(MARCADOR),
    'o marcador tem que aparecer uma unica vez');
});

test('a logica pura nao usa nada do n8n nem do Node', () => {
  const fonte = fs.readFileSync(path.join(__dirname, 'route.js'), 'utf8');
  const pura = fonte.split(MARCADOR)[0];
  for (const proibido of ['$input', '$json', "require(", 'module.exports', 'process.']) {
    assert.equal(pura.includes(proibido), false,
      `a logica pura nao pode conter ${proibido}`);
  }
});
```

- [ ] **Step 2: Rodar e confirmar que passa já (o marcador existe desde a Tarefa 1)**

Run: `MSYS_NO_PATHCONV=1 docker exec chatbot-frontend node --test /n8n/router/contrato.test.js`
Expected: PASS, 2 testes. Se falhar no segundo, `route.js` tem referência proibida e precisa ser corrigido.

- [ ] **Step 3: Substituir `ROUTER_CODE` por leitura do arquivo**

Em `n8n/add_asset_query_branch.py`, apagar o bloco `ROUTER_CODE = r"""..."""` das linhas 15 a 48 e colocar no lugar:

```python
MARCADOR_FIM_LOGICA = "// --- fim da lógica pura; nada abaixo desta linha é injetado no n8n ---"

ROUTER_WRAPPER = """
// O nó anterior é "Buscar Estado da Conversa": uma linha do dataTable, ou nada
// quando a sessão é nova.
const trigger = $('When chat message received').first().json;
const estadoAnterior = $input.first().json || {};
const resultado = route({
  chatInput: trigger.chatInput,
  lastDomain: estadoAnterior.domain,
  allowedDomains: Array.isArray(trigger.allowedDomains) ? trigger.allowedDomains : [],
});
const estadoPreservado = preservarEstado(estadoAnterior, resultado.domain);
return [{ json: { ...trigger, ...resultado, estadoPreservado } }];
""".strip()


def router_code() -> str:
    \"\"\"Monta o jsCode do nó a partir de n8n/router/route.js.

    A lógica pura é a fonte da verdade e vive versionada com testes; aqui só
    acrescentamos o invólucro que fala com o n8n.
    \"\"\"
    fonte = (Path(__file__).parent / "router" / "route.js").read_text(encoding="utf-8")
    if MARCADOR_FIM_LOGICA not in fonte:
        raise SystemExit("route.js sem o marcador de fim da lógica pura.")
    pura = fonte.split(MARCADOR_FIM_LOGICA)[0].rstrip()
    return f"{pura}\n\n{ROUTER_WRAPPER}"
```

- [ ] **Step 4: Trocar os dois usos de `ROUTER_CODE`**

Na linha 215 e na linha 245 do mesmo arquivo, trocar `ROUTER_CODE` por `router_code()`:

```python
        by_name["Roteamento da Consulta"]["parameters"]["jsCode"] = router_code()
```

```python
        node("Roteamento da Consulta", "asset-query-router", "n8n-nodes-base.code", 2, [-2100, -864], {"jsCode": router_code()}),
```

- [ ] **Step 5: Verificar que o script gera o nó com a lógica nova**

Run:
```bash
cd "C:/Users/andre.brito/OneDrive - Gentil Negócios/Área de Trabalho/Projetos/Chat-bot-OM" && \
.venv/Scripts/python.exe n8n/add_asset_query_branch.py \
  n8n/workflows/backup-2026-10-03-gLbok2Xvy09ciYIf-ativo.json \
  scratchpad/wf_patched.json && \
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -c "
import json
d = json.load(open('scratchpad/wf_patched.json', encoding='utf-8'))
no = {n['name']: n for n in d[0]['nodes']}['Roteamento da Consulta']
js = no['parameters']['jsCode']
assert 'chamados_preventiva' in js, 'logica nova nao entrou'
assert 'CAMPOS_COMPARTILHADOS' in js, 'preservacao de estado nao entrou'
assert 'module.exports' not in js, 'module.exports vazou para o no'
assert 'allowedDomains' in js, 'invólucro nao entrou'
assert 'estadoPreservado' in js, 'invólucro nao calcula estadoPreservado'
print('jsCode OK,', len(js), 'chars')
"
```
Expected: `jsCode OK, <n> chars`

- [ ] **Step 6: Commit**

```bash
git add n8n/add_asset_query_branch.py n8n/router/contrato.test.js
git commit -m "refactor(n8n): injetor le o roteador de route.js

O jsCode do no passa a ser gerado a partir do modulo testado, cortado
no marcador de fim da logica pura e somado ao invólucro que fala com o
n8n. Dois testes de contrato garantem que o marcador existe e que a
logica pura nao referencia \$input, require nem process."
```

---

### Task 3: Comprovante assinado carrega os domínios

**Files:**
- Modify: `backend/app/services/asset_query_access.py` (arquivo inteiro, 41 linhas)
- Create: `backend/tests/test_query_access.py`

**Interfaces:**
- Consumes: `INTERNAL_API_KEY` de `app.core.config`.
- Produces: `issue_query_token(session_id: str, user_id: int, domains: list[str]) -> str` e `verify_query_token(token: str, session_id: str, domain: str) -> bool`. Os nomes antigos `issue_asset_query_token` e `verify_asset_query_token` deixam de existir.

- [ ] **Step 1: Escrever o teste, que falha**

Create `backend/tests/test_query_access.py`:

```python
"""Comprovante de consulta: assinatura, validade e domínios."""

import base64
import json
import os
import time

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest

from app.services.asset_query_access import issue_query_token, verify_query_token


SESSAO = "sessao-1"


def test_comprovante_vale_para_os_dominios_emitidos():
    token = issue_query_token(SESSAO, 7, ["ativos", "custos"])

    assert verify_query_token(token, SESSAO, "ativos") is True
    assert verify_query_token(token, SESSAO, "custos") is True


def test_dominio_fora_da_lista_e_recusado():
    token = issue_query_token(SESSAO, 7, ["ativos"])

    assert verify_query_token(token, SESSAO, "custos") is False
    assert verify_query_token(token, SESSAO, "chamados_corretiva") is False


def test_lista_vazia_nao_autoriza_nada():
    token = issue_query_token(SESSAO, 7, [])

    assert verify_query_token(token, SESSAO, "ativos") is False


def test_comprovante_de_outra_sessao_e_recusado():
    token = issue_query_token(SESSAO, 7, ["ativos"])

    assert verify_query_token(token, "outra-sessao", "ativos") is False


def test_dominios_adulterados_quebram_a_assinatura():
    """Reescrever o corpo para incluir custos tem que invalidar o HMAC."""
    token = issue_query_token(SESSAO, 7, ["ativos"])
    corpo, assinatura = token.rsplit(".", 1)
    carga = json.loads(base64.urlsafe_b64decode(corpo.encode() + b"=" * (-len(corpo) % 4)))
    carga["domains"] = ["ativos", "custos"]
    forjado = base64.urlsafe_b64encode(
        json.dumps(carga, separators=(",", ":")).encode()
    ).rstrip(b"=").decode()

    assert verify_query_token(f"{forjado}.{assinatura}", SESSAO, "custos") is False


def test_comprovante_expirado_e_recusado(monkeypatch):
    token = issue_query_token(SESSAO, 7, ["ativos"])
    monkeypatch.setattr(time, "time", lambda: time.time() + 181)

    assert verify_query_token(token, SESSAO, "ativos") is False


@pytest.mark.parametrize("token", ["", "sem-ponto", "a.b", None])
def test_comprovante_malformado_e_recusado(token):
    assert verify_query_token(token, SESSAO, "ativos") is False


def test_comprovante_antigo_sem_dominios_nao_autoriza():
    """Token do formato anterior não tem 'domains'; não pode valer por omissão."""
    carga = {"session_id": SESSAO, "user_id": 7, "exp": int(time.time()) + 180}
    corpo = base64.urlsafe_b64encode(
        json.dumps(carga, separators=(",", ":")).encode()
    ).rstrip(b"=")
    import hashlib
    import hmac

    from app.core.config import INTERNAL_API_KEY

    assinatura = hmac.new(INTERNAL_API_KEY.encode(), corpo, hashlib.sha256).hexdigest()

    assert verify_query_token(f"{corpo.decode()}.{assinatura}", SESSAO, "ativos") is False
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `cd backend && ../.venv/Scripts/python.exe -m pytest tests/test_query_access.py -q`
Expected: FAIL com `ImportError: cannot import name 'issue_query_token'`

- [ ] **Step 3: Reescrever o serviço**

Substituir o conteúdo de `backend/app/services/asset_query_access.py`:

```python
"""Comprovante curto de acesso a consultas para o caminho backend → n8n → backend."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from app.core.config import INTERNAL_API_KEY


VALIDADE_SEGUNDOS = 180


def issue_query_token(session_id: str, user_id: int, domains: list[str]) -> str:
    """Assina quais domínios esta sessão pode consultar, por 3 minutos."""
    if not INTERNAL_API_KEY:
        raise RuntimeError("INTERNAL_API_KEY não configurada.")
    payload = {
        "session_id": session_id,
        "user_id": user_id,
        "domains": sorted(domains),
        "exp": int(time.time()) + VALIDADE_SEGUNDOS,
    }
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).rstrip(b"=")
    signature = hmac.new(INTERNAL_API_KEY.encode(), body, hashlib.sha256).hexdigest()
    return f"{body.decode()}.{signature}"


def verify_query_token(token: str, session_id: str, domain: str) -> bool:
    """Confere assinatura, sessão, validade e se o domínio pedido foi autorizado."""
    if not INTERNAL_API_KEY or not token or "." not in token:
        return False
    body_text, signature = token.rsplit(".", 1)
    body = body_text.encode()
    expected = hmac.new(INTERNAL_API_KEY.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return False
    try:
        payload = json.loads(base64.urlsafe_b64decode(body + b"=" * (-len(body) % 4)))
        domains = payload.get("domains")
        return (
            payload.get("session_id") == session_id
            and isinstance(payload.get("user_id"), int)
            and isinstance(payload.get("exp"), int)
            and time.time() <= payload["exp"]
            # Ausência de "domains" é token do formato antigo: não autoriza nada.
            and isinstance(domains, list)
            and domain in domains
        )
    except (ValueError, TypeError, KeyError):
        return False
```

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `cd backend && ../.venv/Scripts/python.exe -m pytest tests/test_query_access.py -q`
Expected: PASS, 11 testes.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/asset_query_access.py backend/tests/test_query_access.py
git commit -m "feat(backend): comprovante assinado carrega os dominios permitidos

issue_query_token passa a assinar a lista de dominios que a sessao pode
consultar e verify_query_token exige o dominio pedido. Token do formato
antigo, sem o campo domains, deixa de autorizar qualquer coisa, em vez
de valer por omissao.

Os dominios entram no corpo assinado, entao adulterar a lista quebra o
HMAC - coberto por teste."
```

---

### Task 4: Endpoint de ativos commitado com o gate de domínio

**Files:**
- Modify: `backend/app/api/routes/chatbot.py` (as 11 linhas não commitadas)

**Interfaces:**
- Consumes: `verify_query_token` da Tarefa 3; `execute_asset_query` e `AssetQueryRequest`, já no repositório.
- Produces: `POST /chatbot/assets-query` exigindo domínio `ativos`.

- [ ] **Step 1: Verificar o estado não commitado**

Run: `git diff --stat backend/app/api/routes/chatbot.py`
Expected: `1 file changed, 11 insertions(+)` — o endpoint existe só na árvore de trabalho.

- [ ] **Step 2: Ajustar os imports e o gate**

Em `backend/app/api/routes/chatbot.py`, trocar o import e a chamada de verificação:

```python
from app.services.asset_query_access import verify_query_token
```

```python
@router.post("/assets-query", dependencies=[Depends(verificar_internal_api_key)])
def consultar_ativos(payload: AssetQueryRequest, db: Session = Depends(get_db)):
    """Consulta de leitura para o workflow; exige comprovante do domínio ativos."""
    if not verify_query_token(payload.access_token, payload.session_id, "ativos"):
        raise HTTPException(status_code=403, detail="Consulta de ativos não autorizada.")
    return execute_asset_query(db, payload)
```

- [ ] **Step 3: Rodar a suíte inteira do backend**

Run: `cd backend && ../.venv/Scripts/python.exe -m pytest -q`
Expected: PASS. Se algum teste importar `verify_asset_query_token`, corrigir para o nome novo — o símbolo antigo não existe mais.

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/routes/chatbot.py
git commit -m "feat(backend): commita /chatbot/assets-query com gate de dominio

O endpoint existia so na arvore de trabalho: um clone do repositorio
tinha workflow ativo chamando rota ausente. Entra ja exigindo o
dominio ativos no comprovante."
```

---

### Task 5: O backend para de carregar estado de consulta

**Files:**
- Modify: `backend/app/api/routes/assistant.py:58-77` e `:136-158`
- Modify: `backend/app/models/auth.py:136`
- Create: `backend/migrations/versions/20261003_0008_drop_asset_query_state.py`
- Modify: `backend/tests/test_assistant_asset_query.py` (se existir; conferir no Step 1)

**Interfaces:**
- Consumes: `issue_query_token` da Tarefa 3.
- Produces: payload do webhook com `{action, sessionId, chatInput, history, accessToken, allowedDomains}`. Os campos `assetAccessToken`, `assetQueryState` e `hadAssetContext` deixam de ser enviados. A resposta do n8n passa a ser lida só como `output`.

- [ ] **Step 1: Mapear quem usa os símbolos que vão sair**

Run:
```bash
grep -rn "asset_query_state\|hadAssetContext\|assetQueryState\|assetAccessToken\|issue_asset_query_token" backend/
```
Expected: ocorrências em `assistant.py`, `models/auth.py`, `db/migrations.py` e possivelmente testes. Anotar cada uma; todas serão tratadas nesta tarefa.

- [ ] **Step 2: Escrever o teste do payload, que falha**

Em `backend/tests/test_query_access.py`, acrescentar ao fim:

```python
def test_payload_do_webhook_nao_carrega_estado_de_consulta(monkeypatch):
    """O estado vive no dataTable do n8n; o backend só manda a pergunta e o acesso."""
    from app.api.routes import assistant

    capturado = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"output": "ok"}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, json=None, headers=None):
            capturado.update(json or {})
            return FakeResponse()

    monkeypatch.setattr(assistant.httpx, "Client", FakeClient)
    monkeypatch.setattr(assistant, "N8N_CHAT_WEBHOOK_URL", "http://n8n/webhook/x")

    texto = assistant._call_n8n(
        "sessao-1", "quantos chamados abertos?", history=[],
        access_token="tok", allowed_domains=["chamados_corretiva"],
    )

    assert texto == "ok"
    assert capturado["allowedDomains"] == ["chamados_corretiva"]
    assert capturado["accessToken"] == "tok"
    for saiu in ("assetQueryState", "hadAssetContext", "assetAccessToken"):
        assert saiu not in capturado
```

- [ ] **Step 3: Rodar e confirmar que falha**

Run: `cd backend && ../.venv/Scripts/python.exe -m pytest tests/test_query_access.py::test_payload_do_webhook_nao_carrega_estado_de_consulta -q`
Expected: FAIL — `_call_n8n() got an unexpected keyword argument 'access_token'`

- [ ] **Step 4: Reescrever `_call_n8n`**

Substituir as linhas 58-77 de `backend/app/api/routes/assistant.py`:

```python
def _call_n8n(session_id: str, message: str, *, history: list[dict],
              access_token: str | None, allowed_domains: list[str]) -> str:
    if not N8N_CHAT_WEBHOOK_URL:
        raise HTTPException(status_code=503, detail="Assistente não configurado.")
    headers = {"Content-Type": "application/json"}
    if N8N_GATEWAY_TOKEN:
        headers["Authorization"] = f"Bearer {N8N_GATEWAY_TOKEN}"
    with httpx.Client(timeout=120.0) as client:
        resp = client.post(N8N_CHAT_WEBHOOK_URL,
                           json={"action": "sendMessage", "sessionId": session_id,
                                 "chatInput": message, "history": history,
                                 "accessToken": access_token,
                                 "allowedDomains": allowed_domains},
                           headers=headers)
        resp.raise_for_status()
    data = resp.json()
    return (data.get("output") or data.get("text") or data.get("response") or
            data.get("message") or str(data))
```

- [ ] **Step 5: Reescrever o trecho que chamava e persistia**

Substituir as linhas 143-158 de `assistant.py` (do `asset_token = ...` até o `elif asset_state is not None:`):

```python
        permissoes = set(session.permissions or [])
        dominios = []
        if "assets.view" in permissoes:
            dominios.append("ativos")
        if "indicators.view" in permissoes:
            dominios.extend(["chamados_corretiva", "chamados_preventiva", "custos"])
        token = issue_query_token(conversation.n8n_session_id, user.id, dominios) if dominios else None
        assistant_text = _call_n8n(
            conversation.n8n_session_id, content, history=history,
            access_token=token, allowed_domains=sorted(dominios),
        )
```

E trocar o import no topo do arquivo:

```python
from app.services.asset_query_access import issue_query_token
```

- [ ] **Step 6: Remover a coluna do modelo**

Em `backend/app/models/auth.py`, apagar a linha 136:

```python
    asset_query_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
```

Se `JSON` não for mais usado no arquivo, remover também do import do SQLAlchemy.

- [ ] **Step 7: Criar a migração**

Create `backend/migrations/versions/20261003_0008_drop_asset_query_state.py`:

```python
"""Remove assistant_conversations.asset_query_state.

O estado conversacional passa a viver só no dataTable do n8n.

Revision ID: 0008
Revises: 0007
"""

from alembic import op
import sqlalchemy as sa


revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    colunas = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("assistant_conversations")}
    if "asset_query_state" in colunas:
        op.drop_column("assistant_conversations", "asset_query_state")


def downgrade() -> None:
    colunas = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("assistant_conversations")}
    if "asset_query_state" not in colunas:
        op.add_column("assistant_conversations", sa.Column("asset_query_state", sa.JSON(), nullable=True))
```

- [ ] **Step 8: Ajustar o caminho de adoção de banco legado**

Em `backend/app/db/migrations.py:43`, a detecção usa `asset_query_state` para decidir a revisão de stamp. A coluna agora pode não existir num banco novo. Conferir o trecho e garantir que a ausência da coluna não quebre a adoção:

Run: `grep -n -B4 -A10 "has_asset_state" backend/app/db/migrations.py`

A lógica de stamp olha o estado **anterior** do banco, então `has_asset_state` continua correto como detector de bancos antigos. Não alterar; apenas confirmar que o nome da variável segue descrevendo o que detecta.

- [ ] **Step 9: Rodar a suíte inteira do backend**

Run: `cd backend && ../.venv/Scripts/python.exe -m pytest -q`
Expected: PASS. Corrigir qualquer teste que ainda referencie `asset_query_state` ou a assinatura antiga de `_call_n8n`.

- [ ] **Step 10: Aplicar a migração no banco local**

Run: `MSYS_NO_PATHCONV=1 docker exec chatbot-backend alembic upgrade head`
Expected: `Running upgrade 0007 -> 0008`

Run:
```bash
MSYS_NO_PATHCONV=1 docker exec chat-bot-om-db-1 sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -c "SELECT count(*) FROM information_schema.columns WHERE table_name='"'"'assistant_conversations'"'"' AND column_name='"'"'asset_query_state'"'"';"'
```
Expected: `0`

- [ ] **Step 11: Commit**

```bash
git add backend/app/api/routes/assistant.py backend/app/models/auth.py backend/migrations/versions/20261003_0008_drop_asset_query_state.py backend/tests/test_query_access.py
git commit -m "refactor(backend): estado de consulta sai do backend

O payload do webhook perde assetQueryState e hadAssetContext e ganha
accessToken e allowedDomains. O backend deixa de ler, persistir e
compensar estado de consulta - o remendo que preservava contexto de
ativos 'porque o roteamento erra' morre junto com a coluna
assistant_conversations.asset_query_state, removida pela migracao 0008.

Chamados passam a exigir indicators.view, que antes nao era checado no
chat. Aperto deliberado, coerente com o painel que mostra o mesmo dado."
```

---

### Task 6: Colunas novas no `dataTable`

A tabela já tem 117 linhas e 30 colunas. As cinco novas são criadas pela interface do n8n, que escreve em `data_table_column` e na tabela física ao mesmo tempo — fazer isso por SQL direto exige duas escritas coordenadas com o n8n parado, e não vale o risco.

**Files:** nenhum no repositório. O resultado é verificado por consulta.

**Interfaces:**
- Produces: colunas `domain`, `conta_razao`, `periodicity`, `asset_type` e `location` em `chat_query_state`, todas do tipo `string`.

- [ ] **Step 1: Registrar o estado antes**

Run:
```bash
MSYS_NO_PATHCONV=1 docker cp n8n:/home/node/.n8n/database.sqlite scratchpad/n8n-antes.sqlite && \
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -c "
import sqlite3
con = sqlite3.connect('scratchpad/n8n-antes.sqlite')
cur = con.cursor()
print('colunas:', cur.execute('SELECT count(*) FROM data_table_column').fetchone()[0])
print('linhas:', cur.execute('SELECT count(*) FROM data_table_user_Rx2Uo2CukFGRFkgx').fetchone()[0])
"
```
Expected: `colunas: 30` e `linhas: 117`

- [ ] **Step 2: Criar as cinco colunas pela interface do n8n**

Abrir o n8n no navegador, projeto que contém `chat_query_state`
(`/projects/8KNtL2sMcv0bmHfp/datatables/Rx2Uo2CukFGRFkgx`). Para cada nome abaixo,
usar **Add column**, tipo **String**:

| nome | para quê |
|---|---|
| `domain` | o domínio do último turno; é o `lastDomain` do roteador |
| `conta_razao` | filtro de custos (`41140014` ou `41140026`) |
| `periodicity` | filtro de preventiva |
| `asset_type` | filtro de ativos |
| `location` | filtro de ativos |

- [ ] **Step 3: Verificar que as cinco entraram com o tipo certo**

Run:
```bash
MSYS_NO_PATHCONV=1 docker cp n8n:/home/node/.n8n/database.sqlite scratchpad/n8n-depois.sqlite && \
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -c "
import sqlite3
con = sqlite3.connect('scratchpad/n8n-depois.sqlite')
cur = con.cursor()
esperadas = {'domain','conta_razao','periodicity','asset_type','location'}
achadas = {r[0]: r[1] for r in cur.execute('SELECT name, type FROM data_table_column')}
faltando = esperadas - achadas.keys()
assert not faltando, f'faltando: {faltando}'
erradas = {n: achadas[n] for n in esperadas if achadas[n] != 'string'}
assert not erradas, f'tipo errado: {erradas}'
fisicas = {c[1] for c in cur.execute('PRAGMA table_info(data_table_user_Rx2Uo2CukFGRFkgx)')}
assert esperadas <= fisicas, f'nao viraram coluna fisica: {esperadas - fisicas}'
print('as 5 colunas existem, tipo string, na tabela fisica')
print('linhas preservadas:', cur.execute('SELECT count(*) FROM data_table_user_Rx2Uo2CukFGRFkgx').fetchone()[0])
print('linhas com domain preenchido:', cur.execute('SELECT count(*) FROM data_table_user_Rx2Uo2CukFGRFkgx WHERE domain IS NOT NULL').fetchone()[0])
"
```
Expected:
```
as 5 colunas existem, tipo string, na tabela fisica
linhas preservadas: 117
linhas com domain preenchido: 0
```

As 117 linhas com `domain` nulo são exatamente o caso que o teste da Tarefa 1 cobre: o roteador trata nulo como "sem contexto" e cai em `desconhecido`.

- [ ] **Step 4: Guardar o backup pós-alteração**

Run: `cp scratchpad/n8n-depois.sqlite scratchpad/n8n-backup/database-pos-colunas.sqlite`
Expected: sem saída.

Não há commit nesta tarefa: a mudança é de dado, não de código.

---

### Task 7: Workflow religado

**Files:**
- Modify: `n8n/add_asset_query_branch.py` (função `patch_workflow`)

**Interfaces:**
- Consumes: `router_code()` da Tarefa 2.
- Produces: workflow JSON em que `Buscar Estado da Conversa` é o primeiro nó, o roteador lê `estadoAnterior`, o nó de acesso negado é genérico e o Gemini duplicado não existe.

- [ ] **Step 1: Escrever a verificação do religamento, que falha**

Create `scratchpad/verificar_fluxo.py`:

```python
"""Confere a topologia exigida pelo marco 1 num workflow patchado."""

import json
import sys

destino = sys.argv[1]
workflow = json.load(open(destino, encoding="utf-8"))[0]
nos = {n["name"]: n for n in workflow["nodes"]}
conexoes = workflow["connections"]

falhas = []

if "Google Gemini Chat Model1" in nos:
    falhas.append("o no Gemini duplicado ainda existe")

alvos_do_gatilho = [c["node"] for b in conexoes.get("When chat message received", {}).get("main", [[]]) for c in b]
if alvos_do_gatilho != ["Buscar Estado da Conversa"]:
    falhas.append(f"o gatilho deveria ir para Buscar Estado da Conversa, vai para {alvos_do_gatilho}")

alvos_do_estado = [c["node"] for b in conexoes.get("Buscar Estado da Conversa", {}).get("main", [[]]) for c in b]
if alvos_do_estado != ["Roteamento da Consulta"]:
    falhas.append(f"Buscar Estado deveria ir para o roteador, vai para {alvos_do_estado}")

js = nos.get("Roteamento da Consulta", {}).get("parameters", {}).get("jsCode", "")
for exigido in ("chamados_preventiva", "allowedDomains", "estadoPreservado", "CAMPOS_COMPARTILHADOS"):
    if exigido not in js:
        falhas.append(f"jsCode do roteador sem {exigido}")
if "module.exports" in js:
    falhas.append("module.exports vazou para o jsCode")

for ramo, no_merge in (("chamados", "Mesclar Estado da Consulta"), ("ativos", "Mesclar Consulta de Ativos")):
    codigo = nos.get(no_merge, {}).get("parameters", {}).get("jsCode", "")
    if "estadoPreservado" not in codigo:
        falhas.append(f"{no_merge} ({ramo}) nao usa estadoPreservado")

if "Responder Sem Acesso" not in nos:
    falhas.append("falta o no Responder Sem Acesso")

salvar = nos.get("Salvar Estado da Conversa", {})
mapeadas = salvar.get("parameters", {}).get("columns", {}).get("value", {})
if "domain" not in mapeadas:
    falhas.append("Salvar Estado da Conversa nao grava domain")

if falhas:
    print("FALHOU:")
    for f in falhas:
        print("  -", f)
    sys.exit(1)
print("topologia OK")
```

- [ ] **Step 2: Rodar contra o workflow atual e confirmar que falha**

Run:
```bash
.venv/Scripts/python.exe n8n/add_asset_query_branch.py \
  n8n/workflows/backup-2026-10-03-gLbok2Xvy09ciYIf-ativo.json scratchpad/wf_patched.json && \
.venv/Scripts/python.exe scratchpad/verificar_fluxo.py scratchpad/wf_patched.json
```
Expected: FAIL listando o Gemini duplicado, o gatilho apontando para o roteador, e `Salvar Estado` sem `domain`.

- [ ] **Step 3: Religar no `patch_workflow`**

Dentro de `patch_workflow`, antes do `return result`, acrescentar:

```python
    # O roteador precisa do estado para decidir continuidade de domínio, então a
    # leitura do dataTable passa a ser o primeiro nó do fluxo.
    result["connections"]["When chat message received"] = {"main": [[connect("Buscar Estado da Conversa")]]}
    result["connections"]["Buscar Estado da Conversa"] = {"main": [[connect("Roteamento da Consulta")]]}

    # Um único nó de modelo por chain; o duplicado disputava o mesmo input.
    result["nodes"] = [n for n in result["nodes"] if n["name"] != "Google Gemini Chat Model1"]
    result["connections"].pop("Google Gemini Chat Model1", None)

    # O nó de acesso negado deixa de ser só de ativos.
    if "Responder Sem Acesso a Ativos" in by_name:
        negado = by_name["Responder Sem Acesso a Ativos"]
        negado["name"] = "Responder Sem Acesso"
        negado["parameters"]["jsCode"] = (
            "const entrada = $input.first().json;\n"
            "const rotulos = {\n"
            "  ativos: 'a Central de Ativos',\n"
            "  chamados_corretiva: 'os chamados corretivos',\n"
            "  chamados_preventiva: 'os chamados preventivos',\n"
            "  custos: 'os custos de manutenção',\n"
            "};\n"
            "const alvo = rotulos[entrada.deniedDomain] || 'esse assunto';\n"
            "return [{ json: { output: `Você não tem permissão para consultar ${alvo}.` } }];"
        )
        for origem in result["connections"].values():
            for ramo in origem.get("main", []):
                for ligacao in ramo or []:
                    if ligacao["node"] == "Responder Sem Acesso a Ativos":
                        ligacao["node"] = "Responder Sem Acesso"
        result["connections"]["Responder Sem Acesso"] = result["connections"].pop(
            "Responder Sem Acesso a Ativos", {"main": [[]]})

    # O estado salvo passa a registrar o domínio do turno.
    salvar = by_name.get("Salvar Estado da Conversa")
    if salvar:
        salvar["parameters"]["columns"]["value"]["domain"] = "={{ $json.domain }}"
        salvar["parameters"]["columns"]["schema"].append({
            "id": "domain", "displayName": "domain", "required": False,
            "defaultMatch": False, "display": True, "type": "string",
            "readOnly": False, "removed": False,
        })
```

- [ ] **Step 4: Atualizar as condições dos dois IF para os nomes novos**

As condições testam `$json.route`, que agora é `$json.domain`. Em `patch_workflow`, ajustar os dois nós:

```python
    if "Tem Acesso aos Ativos?" in by_name:
        acesso = by_name["Tem Acesso aos Ativos?"]
        acesso["name"] = "Acesso Negado?"
        cond = acesso["parameters"]["conditions"]["conditions"][0]
        cond["leftValue"] = "={{ $json.domain }}"
        cond["rightValue"] = "sem_acesso"
        for origem in result["connections"].values():
            for ramo in origem.get("main", []):
                for ligacao in ramo or []:
                    if ligacao["node"] == "Tem Acesso aos Ativos?":
                        ligacao["node"] = "Acesso Negado?"
        result["connections"]["Acesso Negado?"] = result["connections"].pop("Tem Acesso aos Ativos?", {"main": [[]]})

    if "Consulta de Ativos?" in by_name:
        cond = by_name["Consulta de Ativos?"]["parameters"]["conditions"]["conditions"][0]
        cond["leftValue"] = "={{ $json.domain }}"
        cond["rightValue"] = "ativos"
```

Acrescentar ao `scratchpad/verificar_fluxo.py`, antes do bloco `if falhas:`:

```python
for nome, esperado in (("Acesso Negado?", "sem_acesso"), ("Consulta de Ativos?", "ativos")):
    no = nos.get(nome)
    if not no:
        falhas.append(f"falta o no {nome}")
        continue
    cond = no["parameters"]["conditions"]["conditions"][0]
    if cond["leftValue"] != "={{ $json.domain }}" or cond["rightValue"] != esperado:
        falhas.append(f"{nome} testa {cond['leftValue']} == {cond['rightValue']}")
```

- [ ] **Step 4b: Inspecionar os dois nós de mesclagem antes de alterá-los**

Estes dois nós são os únicos cujo código ainda não foi lido durante o
planejamento. Imprima os dois antes de mexer:

```bash
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -c "
import json
d = json.load(open('n8n/workflows/backup-2026-10-03-gLbok2Xvy09ciYIf-ativo.json', encoding='utf-8'))
nos = {n['name']: n for n in d[0]['nodes']}
for nome in ['Mesclar Estado da Consulta', 'Mesclar Consulta de Ativos']:
    print('=' * 20, nome)
    print(nos[nome]['parameters'].get('jsCode',''))
"
```

Anote, para cada nó, **a expressão que ele usa hoje para obter o estado
anterior**. No ramo de ativos, é alguma forma de
`$('Roteamento da Consulta').first().json.assetQueryState`. No de chamados, é a
leitura do nó do `dataTable`.

- [ ] **Step 4c: Trocar a origem do estado anterior nos dois nós**

Em `patch_workflow`, acrescentar a substituição, usando as expressões anotadas no
passo anterior como `origem`:

```python
    # Os dois nós de mesclagem passam a partir do estado já filtrado pelo
    # roteador, em vez de ler o estado cru. Assim a regra de troca de domínio
    # vale para os dois ramos sem ser duplicada em JS de nó.
    NOVA_ORIGEM = "$('Roteamento da Consulta').first().json.estadoPreservado || {}"
    for nome_no, origens in (
        ("Mesclar Consulta de Ativos", [
            "$('Roteamento da Consulta').first().json.assetQueryState || {}",
            "$('Roteamento da Consulta').first().json.assetQueryState",
        ]),
        ("Mesclar Estado da Consulta", [
            "$('Buscar Estado da Conversa').first().json || {}",
            "$('Buscar Estado da Conversa').first().json",
        ]),
    ):
        no_merge = by_name.get(nome_no)
        if not no_merge:
            continue
        codigo = no_merge["parameters"]["jsCode"]
        for origem in origens:
            if origem in codigo:
                codigo = codigo.replace(origem, NOVA_ORIGEM)
                break
        else:
            raise SystemExit(
                f"{nome_no}: nenhuma das origens conhecidas foi encontrada no jsCode. "
                f"Rode o Step 4b, anote a expressão real e acrescente à lista."
            )
        no_merge["parameters"]["jsCode"] = codigo
```

Se o `SystemExit` disparar, a expressão real difere das previstas: acrescente a
expressão anotada no Step 4b à lista `origens` do nó correspondente e rode de
novo. **Não** remova o `raise` — ele é o que impede o patch de passar em
silêncio sem ter trocado nada.

- [ ] **Step 5: Rodar a verificação e confirmar que passa**

Run:
```bash
.venv/Scripts/python.exe n8n/add_asset_query_branch.py \
  n8n/workflows/backup-2026-10-03-gLbok2Xvy09ciYIf-ativo.json scratchpad/wf_patched.json && \
.venv/Scripts/python.exe scratchpad/verificar_fluxo.py scratchpad/wf_patched.json
```
Expected: `topologia OK`

- [ ] **Step 6: Conferir que o prompt de 85 KB não foi tocado**

Run:
```bash
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -c "
import json
def prompt(p):
    d = json.load(open(p, encoding='utf-8'))
    w = d[0] if isinstance(d, list) else d
    return {n['name']: n for n in w['nodes']}['Interpretar Estado da Consulta']['parameters']['text']
antes = prompt('n8n/workflows/backup-2026-10-03-gLbok2Xvy09ciYIf-ativo.json')
depois = prompt('scratchpad/wf_patched.json')
assert antes == depois, 'o prompt de chamados foi alterado e nao deveria'
print('prompt de 85 KB intacto:', len(depois), 'chars')
"
```
Expected: `prompt de 85 KB intacto: 85660 chars`

- [ ] **Step 7: Commit**

```bash
git add n8n/add_asset_query_branch.py
git commit -m "feat(n8n): religa o fluxo para o roteador de dominios

Buscar Estado da Conversa passa a ser o primeiro no, para o roteador
ler o dominio do turno anterior do proprio dataTable em vez de depender
do backend. Os dois IF passam a testar \$json.domain. O no de acesso
negado deixa de ser so de ativos e nomeia o dominio recusado. O no
Gemini duplicado, que disputava o mesmo input ai_languageModel[0], sai.
Salvar Estado da Conversa passa a gravar domain.

O prompt de 85 KB dos chamados nao e alterado, verificado por
comparacao byte a byte."
```

---

### Task 8: Implantar, verificar ao vivo e limpar

O histórico de publicação mostra sete eventos `deactivated` seguidos e nenhum `activated` desde 25/09, com `workflow_entity.active = 1`. Quem faz o fluxo rodar é a flag `active`, então a verificação não pode ser código de saída de CLI: tem que ser pergunta real respondida.

**Files:**
- Modify: `docs/integracao-ativos-chat.md`

**Interfaces:**
- Consumes: `scratchpad/wf_patched.json` da Tarefa 7.
- Produces: workflow ativo servindo o webhook com o roteamento novo.

- [ ] **Step 1: Importar o workflow patchado**

Run:
```bash
MSYS_NO_PATHCONV=1 docker cp scratchpad/wf_patched.json n8n:/tmp/wf_patched.json && \
MSYS_NO_PATHCONV=1 docker exec n8n n8n import:workflow --input=/tmp/wf_patched.json
```
Expected: `Successfully imported 1 workflow.`

- [ ] **Step 2: Confirmar que o fluxo ficou ativo**

Run:
```bash
MSYS_NO_PATHCONV=1 docker cp n8n:/home/node/.n8n/database.sqlite scratchpad/n8n-pos-import.sqlite && \
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -c "
import sqlite3
con = sqlite3.connect('scratchpad/n8n-pos-import.sqlite')
for r in con.execute('SELECT id, name, active FROM workflow_entity'):
    print(r)
"
```
Expected: `gLbok2Xvy09ciYIf` com `active = 1`. Se vier `0`, o import desativou: rodar `MSYS_NO_PATHCONV=1 docker exec n8n n8n publish:workflow --id=gLbok2Xvy09ciYIf` e repetir esta verificação.

- [ ] **Step 3: Reiniciar o n8n para carregar a versão importada**

Run: `docker compose restart n8n`
Expected: o container reinicia.

Run: `MSYS_NO_PATHCONV=1 docker exec n8n sh -c 'sleep 15; echo pronto'`
Expected: `pronto`

- [ ] **Step 4: Verificar ao vivo — o critério de aceite do marco**

Fazer no chat da aplicação, com um usuário que tenha `assistant.use`, `assets.view` e `indicators.view`, nesta ordem, em conversas **novas**:

| # | pergunta | esperado |
|---|---|---|
| 1 | Quantos chamados estão abertos? | responde sobre chamados corretivos, como antes |
| 2 | E na praça Natal? | mantém o contexto de chamados e filtra por praça |
| 3 | Quantos extintores existem na loja 4006? | responde sobre ativos, como antes |
| 4 | E quantos desses tem no salão de venda? | mantém o contexto de ativos |
| 5 | Quantos chamados preventivos foram concluídos? | diz que não identificou o assunto — preventiva não existe neste marco |
| 6 | Quanto gastamos com manutenção corretiva em agosto? | diz que não identificou o assunto |
| 7 | Qual a capital da França? | diz que não identificou o assunto |

As perguntas 1 a 4 provam que nada regrediu. As 5 a 7 provam que o erro ficou honesto em vez de responder corretiva em silêncio. **Se qualquer uma das quatro primeiras falhar, restaurar o backup e parar.**

- [ ] **Step 5: Verificar o acesso negado**

Com um usuário sem `assets.view`, perguntar "quantos extintores existem?".
Expected: "Você não tem permissão para consultar a Central de Ativos."

Com um usuário sem `indicators.view`, perguntar "quantos chamados estão abertos?".
Expected: "Você não tem permissão para consultar os chamados corretivos."

- [ ] **Step 6: Confirmar que o estado está sendo gravado com domínio**

Run:
```bash
MSYS_NO_PATHCONV=1 docker cp n8n:/home/node/.n8n/database.sqlite scratchpad/n8n-pos-teste.sqlite && \
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -c "
import sqlite3
con = sqlite3.connect('scratchpad/n8n-pos-teste.sqlite')
for r in con.execute('SELECT session_id, domain, praca FROM data_table_user_Rx2Uo2CukFGRFkgx WHERE domain IS NOT NULL ORDER BY updatedAt DESC LIMIT 5'):
    print(r)
"
```
Expected: pelo menos uma linha com `domain` em `chamados_corretiva` ou `ativos`.

- [ ] **Step 7: Apagar o workflow morto e nomear o vivo**

A CLI do n8n 2.39.5 **não tem** `delete:workflow` — os comandos disponíveis são
`list:workflow`, `import:workflow`, `export:workflow`, `publish:workflow`,
`unpublish:workflow` e `update:workflow` (este último depreciado). As duas ações
são pela interface:

1. Apagar (ou arquivar) o fluxo `upI5TZs9209GtPQU`, aquele com 4 nós e inativo.
   O backup está em `n8n/workflows/backup-2026-10-03-upI5TZs9209GtPQU-morto.json`.
2. Renomear o fluxo vivo de "My workflow" para **Chat O&M — Consultas**.

Confirme antes qual é qual, para não apagar o errado — os dois têm o mesmo nome
hoje, e é exatamente por isso que este passo existe:

```bash
MSYS_NO_PATHCONV=1 docker exec n8n n8n list:workflow
```
Expected: duas linhas; o fluxo a apagar é `upI5TZs9209GtPQU`.

Run:
```bash
MSYS_NO_PATHCONV=1 docker cp n8n:/home/node/.n8n/database.sqlite scratchpad/n8n-final.sqlite && \
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -c "
import sqlite3
con = sqlite3.connect('scratchpad/n8n-final.sqlite')
linhas = list(con.execute('SELECT id, name, active FROM workflow_entity'))
print(linhas)
assert len(linhas) == 1, 'deveria sobrar so o fluxo vivo'
assert linhas[0][1] != 'My workflow', 'o fluxo vivo continua sem nome'
assert linhas[0][2] == 1, 'o fluxo vivo nao esta ativo'
print('limpeza OK')
"
```
Expected: `limpeza OK`

- [ ] **Step 8: Atualizar a documentação**

Em `docs/integracao-ativos-chat.md`, substituir a seção **Autorização** e a frase sobre `asset_query_state` para refletir o que passou a valer:

```markdown
## Autorização

O usuário precisa de `assistant.use` para falar no chat. Cada domínio exige a
sua permissão: `assets.view` para ativos, `indicators.view` para chamados,
preventivas e custos. O backend emite um comprovante assinado, válido por três
minutos, listando os domínios autorizados; o n8n o encaminha à API usando a
credencial `X-Internal-API-Key`. Uma pergunta de domínio não autorizado recebe
resposta de falta de permissão nomeando o domínio.

O estado estruturado da conversa vive na tabela `chat_query_state` do n8n, numa
linha por sessão, com a coluna `domain` registrando o domínio do último turno.
O backend não carrega nem persiste estado de consulta.
```

E no diagrama Mermaid, trocar o nó de decisão por `D{Domínio da pergunta}` com as saídas `Ativos`, `Chamados`, `Sem permissão` e `Desconhecido`.

- [ ] **Step 9: Rodar as duas suítes uma última vez**

Run: `cd backend && ../.venv/Scripts/python.exe -m pytest -q`
Expected: PASS

Run: `docker exec chatbot-frontend npm test`
Expected: PASS

- [ ] **Step 10: Commit final do marco**

```bash
git add docs/integracao-ativos-chat.md
git commit -m "docs: contrato do chat com autorizacao por dominio

Autorizacao passa a ser por dominio no comprovante assinado, e o estado
conversacional vive na tabela chat_query_state do n8n com a coluna
domain. O backend nao carrega mais estado de consulta.

Marco 1 verificado ao vivo: chamados e ativos respondem como antes;
preventiva, custos e pergunta fora de assunto caem em desconhecido em
vez de consultar corretiva em silencio."
```

---

## Critério de aceite do marco 1

O marco fecha quando, simultaneamente:

1. `pytest -q` no backend passa inteiro.
2. `npm test` no frontend passa inteiro: 74 testes anteriores, 19 do roteador e 2 de contrato, 95 no total.
3. As perguntas 1 a 4 do Step 4 da Tarefa 8 respondem como antes da mudança.
4. As perguntas 5 a 7 caem em `desconhecido`.
5. As duas verificações de acesso negado do Step 5 respondem nomeando o domínio.
6. `data_table_column` tem as cinco colunas novas e as 117 linhas seguem lá.
7. Sobra um único workflow no n8n, ativo e com nome.

Se 3 falhar, restaurar `n8n/workflows/backup-2026-10-03-gLbok2Xvy09ciYIf-ativo.json` e parar. O marco 2 — preventiva e custos — só começa depois disso tudo verde.
