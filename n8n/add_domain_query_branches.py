"""Acrescenta preventiva e custos ao workflow exportado, preservando os ramos existentes.

Uso: python n8n/add_domain_query_branches.py workflow-atual.json workflow-novo.json
Use uma exportação do workflow publicado como entrada. O arquivo guarda somente
referências a credenciais, nunca a chave de API.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

from add_asset_query_branch import connect, if_node


PREVENTIVE_PROMPT = """=Você interpreta somente perguntas sobre CHAMADOS PREVENTIVOS do app Tape 57532. Extraia JSON conforme o parser; não gere SQL e não responda ao usuário.

Pergunta: {{ $('When chat message received').first().json.chatInput }}
Estado anterior permitido: {{ JSON.stringify($('Roteamento da Consulta').first().json.estadoPreservado || null) }}
Hoje: {{ new Date().toISOString().slice(0, 10) }}

query_shape: count para quantidade simples; list para tickets individuais; group para distribuição por dimensão; ranking para top N/maior. group_by é obrigatório apenas em group/ranking: store_name, praca, status, periodicity, category, subcategory ou supplier. "Quantos por periodicidade?" é group, não count. limit é o N pedido, até 50 em list e 100 em group/ranking.

Filtros disponíveis: store_name, praca, status, periodicity, category, subcategory, supplier, year, month, start_date, end_date, date_field, overdue. Status reais: Backlog, Em Atendimento, Não Aprovado, Serviço Finalizado. "Concluídos" significa status Serviço Finalizado. "Atrasados" significa overdue=true: data prevista vencida e serviço ainda não finalizado; o campo SLA não contém dados nesta base. Periodicidade: Mensal, Trimestral, Semestral, Anual. Datas no formato AAAA-MM-DD. date_field padrão created_on; para conclusão use completion_date, visita visit_date, prazo due_date. Mês e ano usam date_field. Não confunda valor aprovado da Tape com custo SAP.

Se a pergunta for acompanhamento, use follow_up=true e só preencha filtros alterados, deixando os demais null; clear_fields lista filtros removidos explicitamente. "E na praça Natal?" mantém a periodicidade anterior.

Uma pergunta autônoma usa follow_up=false E DEIXA EM null TODO FILTRO QUE ELA MESMA NÃO ENUNCIE. Nunca copie loja, praça, categoria, periodicidade ou período do estado anterior numa pergunta autônoma: o estado serve ao acompanhamento, não é valor padrão. "Quantas preventivas foram concluídas em 2026?", depois de um turno sobre Natal com periodicidade mensal, é pergunta sobre a empresa inteira no ano inteiro — year=2026 e todo o resto null. "Quantas por periodicidade?" usa group_by=periodicity e limpa filtro periodicity. Não invente loja, categoria ou fornecedor; copie os termos do usuário. Preencha todas as chaves do schema, inclusive null e [] quando não usadas."""

COST_PROMPT = """=Você interpreta somente perguntas sobre CUSTOS DE MANUTENÇÃO da extração SAP FBL3N. Extraia JSON conforme o parser; não gere SQL e não responda ao usuário.

Pergunta: {{ $('When chat message received').first().json.chatInput }}
Estado anterior permitido: {{ JSON.stringify($('Roteamento da Consulta').first().json.estadoPreservado || null) }}
Conta razão indicada pelo roteador: {{ $('Roteamento da Consulta').first().json.contaRazao || null }}
Hoje: {{ new Date().toISOString().slice(0, 10) }}

query_shape: count para valor total gasto (a resposta traz valor líquido e número de lançamentos); list para partidas individuais; group para valor POR loja, praça, fornecedor, conta, ano ou mês; ranking para top N/maior custo. group_by: store_name, praca, supplier, conta_razao, year ou month, obrigatório só em group/ranking. limit máximo 50 na listagem e 100 nos grupos.

Filtros: conta_razao, store_name, praca, supplier, year, month, start_date, end_date, unattributed. Conta 41140014 é corretiva; 41140026 é preventiva. A conta razão explícita do roteador prevalece sobre qualquer inferência sua. "Não atribuídos" usa unattributed=true. A competência é a data de lançamento, nunca a data da nota. Estornos já vêm negativos e entram na soma líquida. Não use valor aprovado dos chamados. O SAP NÃO traz categoria, equipamento nem ativo; pedidos de gasto por ar-condicionado, climatização ou outra categoria não podem ser filtrados nesta base. Se o usuário pedir isso, preencha unsupported_filter com a dimensão solicitada; a resposta explicará a limitação sem mostrar um total enganoso.

Se a pergunta for acompanhamento, use follow_up=true e só preencha filtros alterados; clear_fields lista filtros removidos explicitamente. Para "e na praça Natal?", preserve conta e período anteriores.

Uma pergunta autônoma usa follow_up=false E DEIXA EM null TODO FILTRO QUE ELA MESMA NÃO ENUNCIE. Nunca copie loja, praça, fornecedor ou período do estado anterior numa pergunta autônoma: o estado serve ao acompanhamento, não é valor padrão. "Quanto gastamos com manutenção em 2026?", depois de um turno sobre Natal em agosto, é pergunta sobre a empresa inteira no ano inteiro — year=2026 e todo o resto null. "Quais as lojas com maior gasto?" é o ranking geral: group_by=store_name e nenhum filtro de praça, mês ou loja. Responder essas com o escopo do turno anterior devolve uma cifra errada à pergunta que foi feita. "Por fornecedor?" é group_by=supplier, sem filtro de fornecedor. Não invente loja, período ou fornecedor. Preencha todas as chaves do schema, inclusive null e [] quando não usadas."""


def nullable(kind: str, **options) -> dict:
    return {"anyOf": [{"type": kind, **options}, {"type": "null"}]}


def schema(domain: str) -> str:
    common = {
        "follow_up": {"type": "boolean"},
        "clear_fields": {"type": "array", "items": {"type": "string"}},
        "query_shape": {"type": "string", "enum": ["count", "list", "group", "ranking"]},
        "group_by": nullable("string", enum=(
            ["store_name", "praca", "status", "periodicity", "category", "subcategory", "supplier"]
            if domain == "preventive" else
            ["store_name", "praca", "supplier", "conta_razao", "year", "month"]
        )),
        "limit": nullable("integer", minimum=1, maximum=100),
        "store_name": nullable("string"), "praca": nullable("string"),
        "year": nullable("integer", minimum=2000, maximum=2100),
        "month": nullable("integer", minimum=1, maximum=12),
        "start_date": nullable("string"), "end_date": nullable("string"),
        "supplier": nullable("string"),
    }
    if domain == "preventive":
        common.update({
            "status": nullable("string"), "periodicity": nullable("string"),
            "category": nullable("string"), "subcategory": nullable("string"),
            "date_field": nullable("string", enum=["created_on", "completion_date", "visit_date", "due_date"]),
            "overdue": nullable("boolean"),
        })
    else:
        common.update({"conta_razao": nullable("string"), "unattributed": nullable("boolean"),
                       "unsupported_filter": nullable("string")})
    return json.dumps({"type": "object", "additionalProperties": False,
                       "properties": common, "required": list(common)}, ensure_ascii=False, indent=2)


MERGE_TEMPLATE = r"""
const raw = $input.first().json;
const changes = typeof raw.output === 'string' ? JSON.parse(raw.output) : (raw.output || raw);
const trigger = $('Roteamento da Consulta').first().json;
const previous = trigger.estadoPreservado && typeof trigger.estadoPreservado === 'object' ? trigger.estadoPreservado : {};
// A dica do roteador existe para quando o modelo ESQUECE de marcar
// acompanhamento; ela nao pode sobrepor uma negativa explicita, que e o modelo
// dizendo que a pergunta se sustenta sozinha.
const followUp = changes.follow_up === true
  || (changes.follow_up !== false && trigger.followUpHint === true);
// Herda SO em acompanhamento. O "|| !sameDomain" que estava aqui fazia uma
// pergunta nova de custos herdar praca e mes do turno de chamados anterior e
// responder com cifra do escopo errado. O ramo de ativos sempre gateou so em
// followUp; os dois agora concordam.
const preserved = followUp ? previous : {};
const fields = __FIELDS__;
const groups = new Set(__GROUPS__);
const clear = new Set(Array.isArray(changes.clear_fields) ? changes.clear_fields : []);
const query = {};
for (const field of fields) {
  query[field] = clear.has(field) ? null : (changes[field] ?? preserved[field] ?? null);
}
query.query_shape = changes.query_shape || preserved.query_shape || 'count';
query.group_by = ['group','ranking'].includes(query.query_shape) && groups.has(changes.group_by || preserved.group_by)
  ? (changes.group_by || preserved.group_by) : null;
query.limit = ['list','group','ranking'].includes(query.query_shape)
  ? (changes.limit ?? (followUp && preserved.query_shape === query.query_shape ? preserved.limit : null)) : null;
if (query.group_by && Object.prototype.hasOwnProperty.call(query, query.group_by)) query[query.group_by] = null;
__DOMAIN_RULE__
return [{ json: { ...query, session_id: trigger.sessionId, access_token: trigger.accessToken } }];
""".strip()


PREVENTIVE_RESPONSE = r"""
const result = $input.first().json;
const query = $('Mesclar Consulta Preventiva').first().json;
const n = value => Number(value || 0).toLocaleString('pt-BR');
const safe = value => String(value ?? 'Não informado').replace(/\|/g, '\\|').replace(/\r?\n/g, ' ');
const filters = [];
for (const [key,label] of Object.entries({store_name:'loja',praca:'praça',status:'status',periodicity:'periodicidade',category:'categoria',subcategory:'subcategoria',supplier:'fornecedor'})) {
  if (query[key]) filters.push(`${label} ${query[key]}`);
}
if (query.month) filters.push(`mês ${query.month}`);
if (query.year) filters.push(`ano ${query.year}`);
if (query.overdue) filters.push('prazo vencido e não finalizado');
const suffix = filters.length ? ` considerando ${filters.join('; ')}` : '';
let output;
if (result.query_shape === 'count') {
  output = `Encontrei **${n(result.total_count)} chamados preventivos**${suffix} na base da Tape.`;
} else if (result.query_shape === 'list') {
  const rows = result.rows || [];
  output = rows.length ? `Encontrei **${n(result.total_count)} chamados preventivos**${suffix}.\n\n| Ticket | Status | Loja | Praça | Categoria | Periodicidade | Criado em | Prazo |\n|---|---|---|---|---|---|---|---|\n` : `Não encontrei chamados preventivos${suffix}.`;
  for (const row of rows) output += `| ${safe(row.ticket)} | ${safe(row.status)} | ${safe(row.store_name)} | ${safe(row.praca)} | ${safe(row.category)} | ${safe(row.periodicity)} | ${safe(row.created_on?.slice(0,10))} | ${safe(row.due_date?.slice(0,10))} |\n`;
  if (result.truncated) output += '\nA lista foi limitada. Informe loja, praça, período ou status para refinar.';
} else {
  const rows = result.rows || [];
  output = rows.length ? `Chamados preventivos por **${safe(result.group_by)}**${suffix}:\n\n| Grupo | Quantidade |\n|---|---:|\n` : `Não encontrei chamados preventivos${suffix}.`;
  for (const row of rows) output += `| ${safe(row.label)} | ${n(row.total)} |\n`;
  if (result.truncated) output += '\nMostrei apenas os primeiros grupos. Refine os filtros.';
}
return [{json:{output}}];
""".strip()


COST_RESPONSE = r"""
const result = $input.first().json;
const query = $('Mesclar Consulta de Custos').first().json;
const n = value => Number(value || 0).toLocaleString('pt-BR');
const money = value => Number(value || 0).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
const safe = value => String(value ?? 'Não informado').replace(/\|/g, '\\|').replace(/\r?\n/g, ' ');
if (result.unsupported_filter) {
  return [{json:{output:`A extração SAP não identifica ${safe(result.unsupported_filter)} em cada lançamento. Posso consultar custos por loja, praça, fornecedor, conta razão ou mês, sem atribuir esse valor a equipamentos ou chamados.`}}];
}
const filters = [];
if (query.conta_razao) filters.push(`conta razão ${query.conta_razao}`);
if (query.store_name) filters.push(`loja ${query.store_name}`);
if (query.praca) filters.push(`praça ${query.praca}`);
if (query.supplier) filters.push(`fornecedor ${query.supplier}`);
if (query.month) filters.push(`mês ${query.month}`);
if (query.year) filters.push(`ano ${query.year}`);
if (query.unattributed) filters.push('não atribuídos');
const suffix = filters.length ? ` considerando ${filters.join('; ')}` : '';
let output;
if (result.query_shape === 'count') {
  output = result.total_count
    ? `O custo líquido de manutenção foi **${money(result.total_amount)}** em **${n(result.total_count)} lançamentos**${suffix}, pela data de lançamento do SAP. Estornos negativos já reduzem esse total.`
    : `Não encontrei lançamentos de custo${suffix} na base SAP importada. Isso não prova que não houve gastos fora da extração.`;
} else if (result.query_shape === 'list') {
  const rows = result.rows || [];
  output = rows.length ? `Encontrei **${n(result.total_count)} lançamentos**, somando **${money(result.total_amount)}**${suffix}.\n\n| Lançamento | Documento | Loja | Fornecedor | Conta | Valor |\n|---|---|---|---|---|---:|\n` : `Não encontrei lançamentos de custo${suffix} na base SAP importada.`;
  for (const row of rows) output += `| ${safe(row.posting_date)} | ${safe(row.document_number)} | ${safe(row.store_name)} | ${safe(row.supplier)} | ${safe(row.conta_razao)} | ${money(row.amount)} |\n`;
  if (result.truncated) output += '\nA lista foi limitada. Informe loja, praça, período ou fornecedor para refinar.';
} else {
  const rows = result.rows || [];
  output = rows.length ? `Custos líquidos por **${safe(result.group_by)}**${suffix}:\n\n| Grupo | Valor líquido | Lançamentos |\n|---|---:|---:|\n` : `Não encontrei lançamentos de custo${suffix} na base SAP importada.`;
  for (const row of rows) output += `| ${safe(row.label)} | ${money(row.total_amount)} | ${n(row.total)} |\n`;
  if (result.truncated) output += '\nMostrei apenas os primeiros grupos. Refine os filtros.';
}
return [{json:{output}}];
""".strip()


UNKNOWN_RESPONSE = r"""
return [{ json: { output: [
  'Não identifiquei sobre qual assunto você está perguntando.',
  '',
  'Posso consultar:',
  '• chamados corretivos — "quantos chamados estão abertos?"',
  '• chamados preventivos — "quantas preventivas estão em atendimento?"',
  '• ativos — "quantos extintores há na loja 4006?"',
  '• custos de manutenção — "quanto foi gasto em agosto?"',
  '',
  'Reformule citando o assunto e eu busco.',
].join('\n') } }];
""".strip()


def _clone(source: dict, name: str, node_id: str, offset: list[int]) -> dict:
    result = copy.deepcopy(source)
    result["name"] = name
    result["id"] = node_id
    result["position"] = [source["position"][0] + offset[0], source["position"][1] + offset[1]]
    return result


def _save_node(source: dict, name: str, node_id: str, offset: list[int], domain: str) -> dict:
    result = _clone(source, name, node_id, offset)
    fields = ["query_shape", "group_by", "limit", "praca", "store_name", "year", "month",
              "start_date", "end_date", "supplier", "status", "periodicity", "category",
              "subcategory", "date_field", "conta_razao"]
    values = {
        "session_id": "={{ $('When chat message received').first().json.sessionId }}",
        "domain": "={{ $('Roteamento da Consulta').first().json.domain }}",
    }
    for field in fields:
        in_domain = field in ({"status", "periodicity", "category", "subcategory", "date_field"}
                              if domain == "preventive" else {"conta_razao"})
        shared = field in {"query_shape", "group_by", "limit", "praca", "store_name", "year", "month",
                           "start_date", "end_date", "supplier"}
        values[field] = f"={{{{ $json.{field} }}}}" if in_domain or shared else "={{ null }}"
    result["parameters"]["columns"]["value"] = values
    result["parameters"]["columns"]["schema"] = [
        {"id": field, "displayName": field, "required": False, "defaultMatch": False,
         "display": True, "type": "number" if field in {"year", "month", "limit"} else "string",
         "readOnly": False, "removed": False}
        for field in values
    ]
    return result


# Os 16 nós que este script cria. Nomes deterministicos, usados para reaplicar
# sobre a propria saida sem duplicar nem orfanar.
GERADOS = {
    "Interpretar Consulta de Custos", "Google Gemini Custos",
    "Estrutura da Consulta de Custos", "Mesclar Consulta de Custos",
    "Salvar Estado de Custos", "Consultar Custos", "Montar Resposta de Custos",
    "Consulta de Custos?",
    "Interpretar Consulta de Preventivas", "Google Gemini Preventivas",
    "Estrutura da Consulta de Preventivas", "Mesclar Consulta Preventiva",
    "Salvar Estado de Preventivas", "Consultar Preventivas",
    "Montar Resposta de Preventivas", "Consulta de Preventivas?",
}


def patch_workflow(workflow: dict) -> dict:
    result = copy.deepcopy(workflow)
    nodes = {node["name"]: node for node in result["nodes"]}
    required = {"Assunto Desconhecido?", "Consulta de Ativos?", "Interpretar Consulta de Ativos",
                "Google Gemini Ativos", "Estrutura da Consulta de Ativos", "Mesclar Consulta de Ativos",
                "Consultar Ativos", "Salvar Estado de Ativos", "Montar Resposta de Ativos"}
    if not required.issubset(nodes):
        raise ValueError(f"Workflow incompatível; faltam: {sorted(required - set(nodes))}")
    # Idempotente: em vez de recusar, remove os nós que este script gerou antes e
    # reconstrói. Todos são derivados do molde mais parâmetros, então reconstruir
    # é seguro. Recusar deixava qualquer correção no código de mesclagem sem
    # caminho de aplicação: a única saída era rebobinar para um export anterior
    # ao marco 2, perdendo o que tivesse mudado na interface desde então.
    # As posições são preservadas para não desfazer ajuste manual de layout.
    posicoes_anteriores = {
        node["name"]: node["position"]
        for node in result["nodes"] if node["name"] in GERADOS and "position" in node
    }
    if posicoes_anteriores:
        result["nodes"] = [node for node in result["nodes"] if node["name"] not in GERADOS]
        for nome in GERADOS:
            result["connections"].pop(nome, None)
        nodes = {node["name"]: node for node in result["nodes"]}

    for domain, title, offset, endpoint, fields, groups, prompt, response in (
        ("cost", "Custos", [-330, 250], "costs-query",
         ["conta_razao", "store_name", "praca", "supplier", "year", "month",
          "start_date", "end_date", "unattributed", "unsupported_filter"],
         ["store_name", "praca", "supplier", "conta_razao", "year", "month"], COST_PROMPT, COST_RESPONSE),
        ("preventive", "Preventivas", [-110, 520], "preventive-query",
         ["store_name", "praca", "status", "periodicity", "category", "subcategory",
          "supplier", "year", "month", "start_date", "end_date", "date_field", "overdue"],
         ["store_name", "praca", "status", "periodicity", "category", "subcategory", "supplier"],
         PREVENTIVE_PROMPT, PREVENTIVE_RESPONSE),
    ):
        interpreter_name = f"Interpretar Consulta de {title}"
        merge_name = "Mesclar Consulta de Custos" if domain == "cost" else "Mesclar Consulta Preventiva"
        save_name = f"Salvar Estado de {title}"
        http_name = f"Consultar {title}"
        response_name = f"Montar Resposta de {title}"
        model_name = f"Google Gemini {title}"
        parser_name = f"Estrutura da Consulta de {title}"
        prefix = f"{domain}-query"

        interpreter = _clone(nodes["Interpretar Consulta de Ativos"], interpreter_name, prefix + "-interpreter", offset)
        interpreter["parameters"]["text"] = prompt
        model = _clone(nodes["Google Gemini Ativos"], model_name, prefix + "-model", offset)
        parser = _clone(nodes["Estrutura da Consulta de Ativos"], parser_name, prefix + "-parser", offset)
        parser["parameters"]["inputSchema"] = schema(domain)
        merge = _clone(nodes["Mesclar Consulta de Ativos"], merge_name, prefix + "-merge", offset)
        rule = ("if (trigger.contaRazao) query.conta_razao = trigger.contaRazao;\n"
                "const question = String($('When chat message received').first().json.chatInput || '')"
                ".normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toLowerCase();\n"
                "const equipment = question.match(/\\b(ar[ -]?condicionad[oa]s?|climatizac[aã]o|"
                "climatizadores?|splits?|extintores?|equipamentos?|ativos?|"
                "bebedouros?|purificadores?|gelagua|maquinas? de ar|categorias?|"
                "subcategorias?)\\b/);\n"
                "query.unsupported_filter = changes.unsupported_filter || (equipment ? equipment[0] : null);"
                if domain == "cost" else
                "query.date_field = query.date_field || 'created_on';")
        merge["parameters"]["jsCode"] = (MERGE_TEMPLATE.replace("__DOMAIN__", "custos" if domain == "cost" else "chamados_preventiva")
            .replace("__FIELDS__", json.dumps(fields))
            .replace("__GROUPS__", json.dumps(groups))
            .replace("__DOMAIN_RULE__", rule))
        save = _save_node(nodes["Salvar Estado de Ativos"], save_name, prefix + "-save", offset, domain)
        http = _clone(nodes["Consultar Ativos"], http_name, prefix + "-http", offset)
        http["parameters"]["url"] = f"http://backend:8000/chatbot/{endpoint}"
        http["parameters"]["jsonBody"] = f"={{{{ $('{merge_name}').first().json }}}}"
        answer = _clone(nodes["Montar Resposta de Ativos"], response_name, prefix + "-response", offset)
        answer["parameters"]["jsCode"] = response
        result["nodes"].extend([interpreter, model, parser, merge, save, http, answer])
        result["connections"].update({
            model_name: {"ai_languageModel": [[{"node": interpreter_name, "type": "ai_languageModel", "index": 0}]]},
            parser_name: {"ai_outputParser": [[{"node": interpreter_name, "type": "ai_outputParser", "index": 0}]]},
            interpreter_name: {"main": [[connect(merge_name)]]},
            merge_name: {"main": [[connect(save_name)]]},
            save_name: {"main": [[connect(http_name)]]},
            http_name: {"main": [[connect(response_name)]]},
        })

    cost_if = if_node("Consulta de Custos?", "cost-domain-branch", [-1420, -560], "custos")
    prevention_if = if_node("Consulta de Preventivas?", "preventive-domain-branch", [-1210, -330], "chamados_preventiva")
    for item in (cost_if, prevention_if):
        item["parameters"]["conditions"]["conditions"][0]["leftValue"] = "={{ $json.domain }}"
    result["nodes"].extend([cost_if, prevention_if])
    nodes["Responder Assunto Desconhecido"]["parameters"]["jsCode"] = UNKNOWN_RESPONSE
    result["connections"]["Assunto Desconhecido?"]["main"][1] = [connect("Consulta de Custos?")]
    result["connections"]["Consulta de Custos?"] = {"main": [
        [connect("Interpretar Consulta de Custos")], [connect("Consulta de Preventivas?")],
    ]}
    result["connections"]["Consulta de Preventivas?"] = {"main": [
        [connect("Interpretar Consulta de Preventivas")], [connect("Consulta de Ativos?")],
    ]}
    # Devolve as posições que os nós tinham antes de serem reconstruídos.
    for item in result["nodes"]:
        if item["name"] in posicoes_anteriores:
            item["position"] = posicoes_anteriores[item["name"]]
    return result


if __name__ == "__main__":
    source, target = map(Path, sys.argv[1:3])
    raw = json.loads(source.read_text(encoding="utf-8"))
    result = [patch_workflow(raw[0] if isinstance(raw, list) else raw)]
    target.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Workflow com {len(result[0]['nodes'])} nós: {target}")
