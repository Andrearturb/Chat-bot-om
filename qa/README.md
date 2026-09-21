# QA Gentileza

## Objetivo

Este módulo testa a Gentileza de ponta a ponta usando o webhook real do n8n e o banco PostgreSQL de desenvolvimento. Ele valida interpretação, persistência, merge, SQL real gerado pelo agente, resultado do banco, resposta textual final e continuidade entre mensagens.

## Arquitetura

- `qa/runner.py`: executa cenários e produz relatório.
- `qa/n8n_client.py`: envia mensagens ao webhook, com `qaMode` e `qaRunId`.
- `qa/database_client.py`: executa consultas SELECT de oráculo contra o PostgreSQL do ambiente.
- `qa/backend_trace_client.py`: consulta traces gravados em memória pelo backend.
- `qa/validators.py`: valida estados esperados, limites e resultados.
- `qa/diagnostics.py`: classifica falhas em camadas.
- `qa/report.py`: imprime o relatório e salva `qa/reports/latest.json` e `latest.md`.

## Configuração única do n8n

Adicione um node `Code` após o AI Agent chamado `Montar Resposta Final`:

```javascript
const agent = $input.first().json;
const trigger = $('When chat message received').first().json;

const isQa =
  trigger.qaMode === true ||
  String(trigger.qaMode).toLowerCase() === 'true';

const output =
  agent.output ??
  agent.text ??
  agent.response ??
  agent.message ??
  '';

const resposta = {
  output,
};

if (isQa) {
  const interpretationNode = $('Interpretar Estado da Consulta').first().json;

  let interpretation = interpretationNode.output ?? interpretationNode;

  if (typeof interpretation === 'string') {
    try {
      interpretation = JSON.parse(interpretation);
    } catch {
      // manter texto se não for JSON
    }
  }

  resposta.debug = {
    session_id: trigger.sessionId,
    qa_run_id: trigger.qaRunId ?? null,
    previous_state: $('Buscar Estado da Conversa').first().json ?? {},
    interpretation,
    final_state: $('Mesclar Estado da Consulta').first().json ?? {},
  };
}

return [{ json: resposta }];
```

Esse código preserva o payload normal do frontend (`output`) e só emite `debug` quando `qaMode` for verdadeiro.

## Como adicionar `qa_trace_id` no n8n

No node `consultar_banco`, adicione um segundo `Body parameter` chamado `qa_trace_id` em Expression mode com:

```text
{{ $('When chat message received').item.json.qaRunId || '' }}
```

Importante: no editor visual do n8n, não use um `=` literal antes da expressão. O valor deve ser a expressão pronta, sem qualquer prefixo de texto adicional.

Também é essencial não usar `=["Em atendimento"]` em vez do valor real em JSON; o problema clássico foi persistingir a expressão com sintaxe de array quebrada.

## Como executar

### Backend unit tests

```bash
python -m pytest backend/tests -q
```

### Frontend lint

```bash
cd frontend && npm run lint
```

### Frontend build

```bash
cd frontend && npm run build
```

### Runner QA

```bash
python -m qa.runner
```

Com cenário específico:

```bash
python -m qa.runner --scenario current-status-location-continuity
```

Com categoria:

```bash
python -m qa.runner --category temporal
```

PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File qa/run-all.ps1
```

## Como interpretar o relatório

O console e os arquivos em `qa/reports` mostram cenário, passo, camada diagnosticada, SQL real, SQL oráculo e mensagem. A falha é classificada em categorias como `INTERPRETER`, `PERSISTENCE`, `MERGE`, `AI_AGENT_SQL`, `DATABASE_QUERY`, `ASSISTANT_RESPONSE` e `INFRASTRUCTURE`.

## Como adicionar novo cenário

Crie ou atualize um JSON em `qa/scenarios/` com a estrutura:

```json
{
  "id": "novo-cenario",
  "name": "Nome do cenário",
  "category": "temporal",
  "steps": [
    {
      "message": "Quantos chamados...",
      "expected_state": { "event": "current_status", "location_term": "Trairi" },
      "must_be_null": ["date_field", "year"],
      "oracle": { "type": "count", "sql": "SELECT COUNT(*) FROM services WHERE 1 = 1" }
    }
  ]
}
```

## Diagnóstico

As falhas são classificadas pela camada onde a inconsistência apareceu: interpretação do agente, persistência entre mensagens, merge do estado, SQL gerado pelo AI agent, resultado do banco, resposta textual do assistente ou infraestrutura.

## Observação de segurança

O QA é read-only em relação ao banco. Ele consulta o PostgreSQL, coleta traces em memória e não altera dados de produção nem cria uma tabela extra. A ferramenta não imprime segredos como `DATABASE_URL`, `API_KEY` ou senhas.
