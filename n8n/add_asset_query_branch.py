"""Acrescenta a consulta de ativos ao workflow de chat exportado pelo n8n.

Uso: python n8n/add_asset_query_branch.py workflow-original.json workflow-novo.json
O JSON gerado não contém chaves; a credencial HTTP existente permanece por referência.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path


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
    """Monta o jsCode do nó a partir de n8n/router/route.js.

    A lógica pura é a fonte da verdade e vive versionada com testes; aqui só
    acrescentamos o invólucro que fala com o n8n.
    """
    fonte = (Path(__file__).parent / "router" / "route.js").read_text(encoding="utf-8")
    if MARCADOR_FIM_LOGICA not in fonte:
        raise SystemExit("route.js sem o marcador de fim da lógica pura.")
    pura = fonte.split(MARCADOR_FIM_LOGICA)[0].rstrip()
    return f"{pura}\n\n{ROUTER_WRAPPER}"

ASSET_PROMPT = """=Você interpreta perguntas sobre a Central de Ativos do Grupo Gentil. Extraia parâmetros estruturados; não gere SQL nem responda ao usuário. Preencha TODAS as propriedades do JSON Schema.

Mensagem atual: {{ $('When chat message received').first().json.chatInput }}
Estado estruturado da última consulta de ativos: {{ JSON.stringify($('Roteamento da Consulta').first().json.estadoPreservado || null) }}
Data atual: {{ new Date().toISOString().slice(0, 10) }}

Os cadastros são climatização (ar-condicionado, ar condicionados, split, máquinas de ar, BTU), incêndio (extintor) e água (purificador, gelágua, bebedouro). asset_types=[] significa todos os tipos. Nunca trate chamado ou ticket como ativo.

query_shape=count para total simples; list para equipamentos individuais ("quais aparelhos", "liste os extintores"); group para quantidade ou nomes distintos POR loja/praça/tipo/status/marca/localização; ranking para "top N", "qual loja tem mais". Em group/ranking, group_by é obrigatório e pode ser asset_type, store_name, praca, status, equipment_type, brand ou location. "Quais as localizações dos ativos?" é group_by=location, NÃO list. "Quantos são no salão?" é count com location="salão". Para list, limite máximo 50. Use null para campos não pedidos.

Mapeie nome de loja (por extenso, ex.: "ER Parnamirim", "Natal Shopping") em store_name e praça em praca; não invente nomes. Se o usuário citar um código numérico ou curto para identificar a loja (ex.: "loja 4006", "código 21232", "a 4032") SEM dizer se é BPCS ou SAP, use store_code (não store_name) — o sistema busca esse código nos dois cadastros. Só use bpcs_number ou sap_number quando o usuário disser explicitamente qual dos dois sistemas é ("código BPCS 21232", "SAP 4032"). Filtre equipment_type apenas quando o usuário disser um tipo específico como Split, Extintor ou Purificador. "Ar-condicionado" e "máquinas de ar condicionado" correspondem a asset_types=["climatization"] sem equipment_type. Mapeie capacidade como capacity_btu_min/max; "acima de 18000 BTU" significa min=18001, "até 18000" significa max=18000. Vencimento de extintores e próxima troca de filtros de água usam due_before (AAAA-MM-DD); "vencidos" significa até hoje. Outros ativos não têm esse campo.

Se a mensagem depende da consulta anterior ("e em Mossoró?", "quantos são no salão de venda?", "quais as localizações dos ativos?"), use follow_up=true. Nesse caso, informe APENAS os filtros alterados na mensagem atual; deixe os demais null e asset_types=[]. O próximo nó preservará os filtros anteriores automaticamente. Use clear_fields para retirar filtros explicitamente ou ao enumerar aquela dimensão. Exemplo: após consultar 9 aparelhos de climatização na loja ER Parnamirim, "quantos são no salão de venda?" -> follow_up=true, query_shape=count, location="salão de venda", asset_types=[], store_name=null, clear_fields=[]. "Quais as localizações dos ativos?" -> follow_up=true, query_shape=group, group_by=location, clear_fields=["location"].

Uma pergunta completa e independente usa follow_up=false e substitui todos os filtros anteriores. "Quantos ativos existem?" é independente. Não use histórico de chamados para filtrar ativos. Copie nomes de loja do usuário; não invente sinônimos de lojas.
"""

def nullable(type_name: str, **extra):
    return {"anyOf": [{"type": type_name, **extra}, {"type": "null"}]}


ASSET_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "follow_up": {"type": "boolean"},
        "clear_fields": {"type": "array", "items": {"type": "string", "enum": [
            "asset_types", "store_name", "praca", "status", "equipment_type", "location", "brand",
            "asset_code", "bpcs_number", "sap_number", "store_code", "capacity_btu_min", "capacity_btu_max", "due_before",
        ]}, "uniqueItems": True},
        "query_shape": {"type": "string", "enum": ["count", "list", "group", "ranking"]},
        "asset_types": {"type": "array", "items": {"type": "string", "enum": ["climatization", "fire_safety", "water"]}, "uniqueItems": True},
        **{key: nullable("string") for key in (
            "store_name", "praca", "status", "equipment_type", "location", "brand",
            "asset_code", "bpcs_number", "sap_number", "store_code", "due_before",
        )},
        "capacity_btu_min": nullable("integer", minimum=0),
        "capacity_btu_max": nullable("integer", minimum=0),
        "group_by": nullable("string", enum=["asset_type", "store_name", "praca", "status", "equipment_type", "brand", "location"]),
        "limit": nullable("integer", minimum=1, maximum=100),
    },
}
ASSET_SCHEMA["required"] = list(ASSET_SCHEMA["properties"])

ASSET_MERGE_CODE = r"""
const raw = $input.first().json;
const changes = typeof raw.output === 'string' ? JSON.parse(raw.output) : (raw.output || raw);
const trigger = $('Roteamento da Consulta').first().json;
const previous = trigger.estadoPreservado && typeof trigger.estadoPreservado === 'object' ? trigger.estadoPreservado : null;
const followUp = Boolean(previous) && (changes.follow_up === true || trigger.followUpHint === true);
const fields = ['asset_types','store_name','praca','status','equipment_type','location','brand','asset_code','bpcs_number','sap_number','store_code','capacity_btu_min','capacity_btu_max','due_before'];
const clear = new Set(Array.isArray(changes.clear_fields) ? changes.clear_fields : []);
const query = {query_shape: changes.query_shape};
for (const field of fields) {
  const incoming = changes[field];
  const blank = incoming == null || (field === 'asset_types' && Array.isArray(incoming) && incoming.length === 0);
  if (clear.has(field)) query[field] = field === 'asset_types' ? [] : null;
  else if (followUp && blank) query[field] = previous[field] ?? (field === 'asset_types' ? [] : null);
  else query[field] = incoming ?? (field === 'asset_types' ? [] : null);
}
query.group_by = ['group','ranking'].includes(query.query_shape)
  ? (changes.group_by || (followUp ? previous.group_by : null)) : null;
query.limit = ['list','group','ranking'].includes(query.query_shape)
  ? (changes.limit ?? (followUp && previous.query_shape === query.query_shape ? previous.limit : null)) : null;
// Ao enumerar uma dimensão, o filtro anterior da própria dimensão sai do escopo.
if (query.group_by && Object.prototype.hasOwnProperty.call(query, query.group_by)) {
  query[query.group_by] = null;
}
return [{json:{...query,session_id:trigger.sessionId,access_token:trigger.accessToken}}];
""".strip()

ASSET_BODY = "={{ $('Mesclar Consulta de Ativos').first().json }}"

ASSET_RESPONSE_CODE = r"""
const result = $input.first().json;
const query = $('Mesclar Consulta de Ativos').first().json;
const types = {climatization:'climatização',fire_safety:'incêndio',water:'água'};
const fields = {asset_type:'tipo de ativo',store_name:'loja',praca:'praça',status:'status',equipment_type:'tipo de equipamento',brand:'marca',location:'local'};
const safe = value => String(value ?? 'Não informado').replace(/\|/g, '\\|').replace(/\r?\n/g, ' ');
const number = value => Number(value || 0).toLocaleString('pt-BR');
const filters = [];
if (query.asset_types?.length) filters.push(query.asset_types.map(type => types[type] || type).join(', '));
if (query.store_name) filters.push(`loja ${query.store_name}`);
if (query.praca) filters.push(`praça ${query.praca}`);
if (query.status) filters.push(`status ${query.status}`);
if (query.equipment_type) filters.push(`equipamento ${query.equipment_type}`);
if (query.brand) filters.push(`marca ${query.brand}`);
if (query.location) filters.push(`local ${query.location}`);
if (query.asset_code) filters.push(`código ${query.asset_code}`);
if (query.store_code) filters.push(`código de loja ${query.store_code}`);
if (query.bpcs_number) filters.push(`BPCS ${query.bpcs_number}`);
if (query.sap_number) filters.push(`SAP ${query.sap_number}`);
if (query.capacity_btu_min != null) filters.push(`a partir de ${number(query.capacity_btu_min)} BTU`);
if (query.capacity_btu_max != null) filters.push(`até ${number(query.capacity_btu_max)} BTU`);
if (query.due_before) filters.push(`vencimento ou troca de filtro até ${query.due_before}`);
const suffix = filters.length ? ` considerando ${filters.join('; ')}` : '';
let output;
if (result.query_shape === 'count') {
  const total = Number(result.total_count || 0);
  output = `Encontrei **${number(total)} ${total === 1 ? 'ativo' : 'ativos'}**${suffix} na Central de Ativos.`;
  if (Array.isArray(result.matched_locations) && result.matched_locations.length) {
    const matched = result.matched_locations.map(item => `**${safe(item.location)}** (${number(item.total)})`).join(', ');
    output += ` ${result.matched_locations.length === 1 ? 'Local cadastrado encontrado' : 'Locais cadastrados encontrados'}: ${matched}.`;
  }
} else if (result.query_shape === 'list') {
  const rows = Array.isArray(result.rows) ? result.rows : [];
  output = rows.length ? `Encontrei **${number(result.total_count)} ativos**${suffix}.\n\n` : `Não encontrei ativos${suffix}.`;
  if (rows.length) {
    output += '| Código | Tipo | Loja | Equipamento | Local | Status | Detalhes |\n|---|---|---|---|---|---|---|\n';
    for (const row of rows) {
      const detail = [row.brand, row.model, row.capacity_btu ? `${number(row.capacity_btu)} BTU` : null,
        row.expiration_date ? `Vence ${row.expiration_date}` : null,
        row.next_filter_change ? `Troca de filtro ${row.next_filter_change}` : null].filter(Boolean).join(', ');
      output += `| ${safe(row.asset_code)} | ${safe(types[row.asset_type] || row.asset_type)} | ${safe(row.store_name)} | ${safe(row.equipment_type)} | ${safe(row.location)} | ${safe(row.status)} | ${safe(detail || '—')} |\n`;
    }
    if (result.truncated) output += '\nA lista foi limitada. Informe loja, praça ou tipo para refinar a consulta.';
  }
} else {
  const rows = Array.isArray(result.rows) ? result.rows : [];
  const label = fields[result.group_by] || result.group_by || 'grupo';
  output = rows.length ? `Distribuição de ativos por **${label}**${suffix}:\n\n| ${label} | Quantidade |\n|---|---:|\n` : `Não encontrei ativos${suffix}.`;
  for (const row of rows) {
    let name = row[result.group_by];
    if (result.group_by === 'asset_type') name = types[name] || name;
    output += `| ${safe(name)} | ${number(row.total)} |\n`;
  }
  if (result.truncated) output += '\nMostrei apenas os primeiros grupos. Refine os filtros para ver menos grupos.';
}
const {session_id,access_token,...asset_query_state} = query;
return [{json:{output,asset_query_state}}];
""".strip()


def node(name: str, node_id: str, type_name: str, version: float, position: list[int], parameters: dict):
    return {"id": node_id, "name": name, "type": type_name, "typeVersion": version,
            "position": position, "parameters": parameters}


def if_node(name: str, node_id: str, position: list[int], value: str):
    return node(name, node_id, "n8n-nodes-base.if", 2.3, position, {
        "conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
                       "combinator": "and", "conditions": [{
                           "id": node_id + "-condition", "leftValue": "={{ $json.route }}",
                           "rightValue": value, "operator": {"type": "string", "operation": "equals"},
                       }]}, "options": {},
    })


def connect(target: str, index: int = 0):
    return {"node": target, "type": "main", "index": index}


ROTEADOR_DOMAIN = "={{ $('Roteamento da Consulta').first().json.domain }}"

# Colunas que o ramo de ativos persiste para o acompanhamento do turno seguinte.
# asset_types é array e a coluna do dataTable é texto, então vai como JSON e o
# nó de mesclagem o desserializa na leitura.
SALVAR_ATIVOS_VALORES = {
    "session_id": "={{ $('When chat message received').first().json.sessionId }}",
    "domain": ROTEADOR_DOMAIN,
    "query_shape": "={{ $json.query_shape }}",
    "group_by": "={{ $json.group_by }}",
    "limit": "={{ $json.limit }}",
    "praca": "={{ $json.praca }}",
    "store_name": "={{ $json.store_name }}",
    "location": "={{ $json.location }}",
    "asset_type": "={{ JSON.stringify($json.asset_types || []) }}",
    # Sem estas oito, um acompanhamento perdia "extintor" e "loja 4006" e
    # respondia mais amplo do que a pergunta anterior, citando menos filtros.
    # status ja tinha coluna desde o inicio e so nao estava mapeado aqui.
    "status": "={{ $json.status }}",
    "equipment_type": "={{ $json.equipment_type }}",
    "store_code": "={{ $json.store_code }}",
    "brand": "={{ $json.brand }}",
    "asset_code": "={{ $json.asset_code }}",
    "bpcs_number": "={{ $json.bpcs_number }}",
    "sap_number": "={{ $json.sap_number }}",
    "capacity_btu_min": "={{ $json.capacity_btu_min }}",
    "capacity_btu_max": "={{ $json.capacity_btu_max }}",
}

# Reidrata o estado antes do merge usar previous: as colunas do dataTable sao
# texto, mas asset_types e um array e as capacidades em BTU sao numeros que a
# API valida como inteiro.
ATIVOS_PARSE_TIPOS = """
if (previous && typeof previous.asset_type === 'string' && previous.asset_type) {
  try { previous.asset_types = JSON.parse(previous.asset_type); }
  catch (erro) { previous.asset_types = []; }
}
if (previous) {
  for (const campo of ['capacity_btu_min', 'capacity_btu_max']) {
    if (previous[campo] === null || previous[campo] === undefined || previous[campo] === '') continue;
    const numero = Number(previous[campo]);
    previous[campo] = Number.isFinite(numero) ? numero : null;
  }
}
"""

DESCONHECIDO_CODE = r"""
return [{ json: { output: [
  'Não identifiquei sobre qual assunto você está perguntando.',
  '',
  'Posso consultar:',
  '• chamados corretivos — "quantos chamados estão abertos?"',
  '• chamados preventivos — "quantas preventivas estão em atendimento?"',
  '• ativos — "quantos extintores tem na loja 4006?"',
  '• custos de manutenção — "quanto foi gasto em agosto?"',
  '',
  'Reformule citando o assunto e eu busco.',
].join('\n') } }];
""".strip()

NEGADO_CODE = r"""
const entrada = $input.first().json;
const rotulos = {
  ativos: 'a Central de Ativos',
  chamados_corretiva: 'os chamados corretivos',
  chamados_preventiva: 'os chamados preventivos',
  custos: 'os custos de manutenção',
};
const alvo = rotulos[entrada.deniedDomain] || 'esse assunto';
return [{ json: { output: `Você não tem permissão para consultar ${alvo}.` } }];
""".strip()


def _renomear_destino(result: dict, antigo: str, novo: str) -> None:
    """Aponta para o nome novo em todas as ligações e move a chave de saída."""
    for origem in result["connections"].values():
        for ramo in origem.get("main", []):
            for ligacao in ramo or []:
                if ligacao.get("node") == antigo:
                    ligacao["node"] = novo
    if antigo in result["connections"]:
        result["connections"][novo] = result["connections"].pop(antigo)


def _religar_marco1(result: dict) -> dict:
    """Topologia do marco 1: estado antes do roteador, dominio no IF e no
    estado salvo, no de acesso negado generico, sem no de modelo duplicado."""
    # ── Marco 1: religamento ────────────────────────────────────────────────
    # O roteador precisa do estado para decidir continuidade de domínio, então a
    # leitura do dataTable passa a ser o primeiro nó do fluxo.
    result["connections"]["When chat message received"] = {"main": [[connect("Buscar Estado da Conversa")]]}
    result["connections"]["Buscar Estado da Conversa"] = {"main": [[connect("Roteamento da Consulta")]]}

    # Os dois nós Gemini de "Interpretar Estado da Consulta" NÃO são duplicados:
    # Google Gemini Chat Model1 é o modelo principal, em ai_languageModel índice
    # 0 (gemini-3.5-flash-lite), e Google Gemini Chat Model é o fallback, no
    # índice 1, porque o nó tem needsFallback=True. Remover o do índice 0 derruba
    # a cadeia com "A Model sub-node must be connected and enabled". Nenhum dos
    # dois sai daqui.

    by_name = {item["name"]: item for item in result["nodes"]}

    # Os dois IF passam a testar o domínio resolvido pelo roteador.
    if "Tem Acesso aos Ativos?" in by_name:
        acesso = by_name["Tem Acesso aos Ativos?"]
        acesso["name"] = "Acesso Negado?"
        condicao = acesso["parameters"]["conditions"]["conditions"][0]
        condicao["leftValue"] = "={{ $json.domain }}"
        condicao["rightValue"] = "sem_acesso"
        _renomear_destino(result, "Tem Acesso aos Ativos?", "Acesso Negado?")

    if "Consulta de Ativos?" in by_name:
        condicao = by_name["Consulta de Ativos?"]["parameters"]["conditions"]["conditions"][0]
        condicao["leftValue"] = "={{ $json.domain }}"
        condicao["rightValue"] = "ativos"

    # O nó de acesso negado deixa de ser só de ativos e nomeia o domínio recusado.
    if "Responder Sem Acesso a Ativos" in by_name:
        negado = by_name["Responder Sem Acesso a Ativos"]
        negado["name"] = "Responder Sem Acesso"
        negado["parameters"]["jsCode"] = NEGADO_CODE
        _renomear_destino(result, "Responder Sem Acesso a Ativos", "Responder Sem Acesso")

    # O estado salvo passa a registrar o domínio do turno.
    salvar = by_name.get("Salvar Estado da Conversa")
    if salvar:
        # domain tem de vir do roteador por referência de nó: aqui $json é a
        # saída do Mesclar, que devolve o estado de consulta mesclado e não
        # carrega domain — gravava a coluna vazia, e o turno seguinte perdia o
        # contexto por não ter lastDomain.
        salvar["parameters"]["columns"]["value"]["domain"] = ROTEADOR_DOMAIN
        if not any(c.get("id") == "domain" for c in salvar["parameters"]["columns"]["schema"]):
            salvar["parameters"]["columns"]["schema"].append({
                "id": "domain", "displayName": "domain", "required": False,
                "defaultMatch": False, "display": True, "type": "string",
                "readOnly": False, "removed": False,
            })

    # Os dois nós de mesclagem partem do estado já filtrado pelo roteador.
    mesclar = by_name.get("Mesclar Estado da Consulta")
    if mesclar:
        origem = "$('Buscar Estado da Conversa').first().json ?? {}"
        destino = "$('Roteamento da Consulta').first().json.estadoPreservado ?? {}"
        codigo = mesclar["parameters"]["jsCode"]
        if origem not in codigo and destino not in codigo:
            raise SystemExit(
                "Mesclar Estado da Consulta: nao achei "
                f"{origem!r} no jsCode. Inspecione o no e ajuste esta origem."
            )
        mesclar["parameters"]["jsCode"] = codigo.replace(origem, destino)

    # O ramo de chamados entra em Interpretar Estado da Consulta, não em Buscar
    # Estado: a leitura do dataTable virou o primeiro nó do fluxo, e manter a
    # saída falsa apontando para ela fecharia o ciclo
    # Buscar Estado -> Roteamento -> IF -> Buscar Estado, que pendura a execução.
    result["connections"]["Consulta de Ativos?"] = {"main": [
        [connect("Interpretar Consulta de Ativos")],
        [connect("Interpretar Estado da Consulta")],
    ]}

    # Rota desconhecida: sem ela, toda pergunta que não casa com nenhum domínio
    # cai no ramo de chamados e é respondida como se fosse corretiva — o defeito
    # que este marco existe para corrigir.
    # by_name foi montado antes das renomeações acima, que mudaram os nomes no
    # próprio dicionário de nó; sem remontar, as chaves novas não existem.
    by_name = {item["name"]: item for item in result["nodes"]}
    if "Assunto Desconhecido?" not in by_name:
        base = by_name["Acesso Negado?"]["position"]
        result["nodes"].append(if_node(
            "Assunto Desconhecido?", "unknown-domain-branch",
            [base[0] + 160, base[1] + 240], "desconhecido",
        ))
        result["nodes"].append(node(
            "Responder Assunto Desconhecido", "unknown-domain-reply",
            "n8n-nodes-base.code", 2, [base[0] + 420, base[1] + 240],
            {"jsCode": DESCONHECIDO_CODE},
        ))
    by_name = {item["name"]: item for item in result["nodes"]}
    condicao = by_name["Assunto Desconhecido?"]["parameters"]["conditions"]["conditions"][0]
    condicao["leftValue"] = "={{ $json.domain }}"
    condicao["rightValue"] = "desconhecido"
    by_name["Responder Assunto Desconhecido"]["parameters"]["jsCode"] = DESCONHECIDO_CODE

    # O ramo de ativos não tinha nó de salvar: o estado vinha do backend, que
    # deixou de carregá-lo. Sem isto, acompanhamento de ativos perde o contexto.
    mesclar_ativos = by_name.get("Mesclar Consulta de Ativos")
    if salvar and mesclar_ativos and "Salvar Estado de Ativos" not in by_name:
        salvar_ativos = copy.deepcopy(salvar)
        salvar_ativos["name"] = "Salvar Estado de Ativos"
        salvar_ativos["id"] = "asset-state-save"
        base = mesclar_ativos["position"]
        salvar_ativos["position"] = [base[0] + 170, base[1] + 190]
        salvar_ativos["parameters"]["columns"]["value"] = dict(SALVAR_ATIVOS_VALORES)
        salvar_ativos["parameters"]["columns"]["schema"] = [
            {"id": nome, "displayName": nome, "required": False, "defaultMatch": False,
             "display": True, "type": "number" if nome == "limit" else "string",
             "readOnly": False, "removed": False}
            for nome in SALVAR_ATIVOS_VALORES
        ]
        result["nodes"].append(salvar_ativos)

    # Reafirmado fora da criação: patch_workflow religa Mesclar -> Consultar
    # Ativos antes daqui, e numa segunda passada o nó de salvar já existe, então
    # o bloco acima não corrigiria a ligação.
    if "Salvar Estado de Ativos" in {item["name"] for item in result["nodes"]}:
        result["connections"]["Mesclar Consulta de Ativos"] = {"main": [[connect("Salvar Estado de Ativos")]]}
        result["connections"]["Salvar Estado de Ativos"] = {"main": [[connect("Consultar Ativos")]]}

    # O merge de ativos precisa reidratar asset_types, que foi persistido como JSON.
    if mesclar_ativos:
        codigo = mesclar_ativos["parameters"]["jsCode"]
        marca = "const followUp ="
        if ATIVOS_PARSE_TIPOS.strip() not in codigo:
            if marca not in codigo:
                raise SystemExit("Mesclar Consulta de Ativos: nao achei onde inserir o parse de asset_types.")
            codigo = codigo.replace(marca, ATIVOS_PARSE_TIPOS.strip() + "\n" + marca, 1)
            mesclar_ativos["parameters"]["jsCode"] = codigo

    # Acesso negado primeiro, depois assunto desconhecido, depois o domínio.
    result["connections"]["Acesso Negado?"] = {"main": [
        [connect("Responder Sem Acesso")],
        [connect("Assunto Desconhecido?")],
    ]}
    # Preserva a cascata de domínio quando ela já existe. Fixar a saída falsa em
    # "Consulta de Ativos?" fazia este script, rodado sobre um workflow do marco
    # 2, pular os IF de custos e preventiva e orfanar os 14 nós desses ramos — e
    # o add_domain_query_branches.py se recusa a reaplicar, então não havia
    # reparo suportado.
    CASCATA = ["Consulta de Custos?", "Consulta de Preventivas?", "Consulta de Ativos?"]
    nomes_atuais = {item["name"] for item in result["nodes"]}
    entrada_cascata = next((no for no in CASCATA if no in nomes_atuais), "Consulta de Ativos?")
    result["connections"]["Assunto Desconhecido?"] = {"main": [
        [connect("Responder Assunto Desconhecido")],
        [connect(entrada_cascata)],
    ]}

    return result


def patch_workflow(workflow: dict) -> dict:
    result = copy.deepcopy(workflow)
    by_name = {item["name"]: item for item in result["nodes"]}
    required = {"When chat message received", "Buscar Estado da Conversa",
                "Interpretar Estado da Consulta", "Google Gemini Chat Model1",
                "Structured Output Parser", "Consultar Query Estruturada"}
    if not required.issubset(by_name):
        raise ValueError(f"Workflow de chat incompatível: faltam {sorted(required - set(by_name))}.")
    if "Roteamento da Consulta" in by_name:
        required_asset = {"Interpretar Consulta de Ativos", "Estrutura da Consulta de Ativos",
                          "Consultar Ativos", "Montar Resposta de Ativos"}
        if not required_asset.issubset(by_name):
            raise ValueError("Ramificação de ativos incompleta; revise a exportação antes de atualizar.")
        by_name["Roteamento da Consulta"]["parameters"]["jsCode"] = router_code()
        by_name["Interpretar Consulta de Ativos"]["parameters"]["text"] = ASSET_PROMPT
        by_name["Interpretar Consulta de Ativos"]["parameters"]["needsFallback"] = False
        by_name["Estrutura da Consulta de Ativos"]["parameters"]["inputSchema"] = json.dumps(ASSET_SCHEMA, ensure_ascii=False, indent=2)
        by_name["Consultar Ativos"]["parameters"]["jsonBody"] = ASSET_BODY
        by_name["Montar Resposta de Ativos"]["parameters"]["jsCode"] = ASSET_RESPONSE_CODE
        if "Mesclar Consulta de Ativos" not in by_name:
            position = by_name["Consultar Ativos"]["position"]
            result["nodes"].append(node("Mesclar Consulta de Ativos", "asset-query-merge",
                                        "n8n-nodes-base.code", 2, position.copy(), {"jsCode": ASSET_MERGE_CODE}))
            for name in ("Consultar Ativos", "Montar Resposta de Ativos"):
                by_name[name]["position"][0] += 300
        else:
            by_name["Mesclar Consulta de Ativos"]["parameters"]["jsCode"] = ASSET_MERGE_CODE
        result["connections"]["Interpretar Consulta de Ativos"] = {"main": [[connect("Mesclar Consulta de Ativos")]]}
        result["connections"]["Mesclar Consulta de Ativos"] = {"main": [[connect("Consultar Ativos")]]}
        return _religar_marco1(result)
    existing_query = by_name["Consultar Query Estruturada"]
    credential = copy.deepcopy(existing_query["credentials"])
    model = copy.deepcopy(by_name["Google Gemini Chat Model1"])
    model.update(id="asset-gemini-model", name="Google Gemini Ativos", position=[-1550, -900])
    parser = copy.deepcopy(by_name["Structured Output Parser"])
    parser.update(id="asset-output-parser", name="Estrutura da Consulta de Ativos", position=[-1320, -900])
    parser["parameters"]["inputSchema"] = json.dumps(ASSET_SCHEMA, ensure_ascii=False, indent=2)
    ai = copy.deepcopy(by_name["Interpretar Estado da Consulta"])
    ai.update(id="asset-query-interpreter", name="Interpretar Consulta de Ativos", position=[-1600, -1180])
    ai["parameters"]["text"] = ASSET_PROMPT
    ai["parameters"]["needsFallback"] = False

    new_nodes = [
        node("Roteamento da Consulta", "asset-query-router", "n8n-nodes-base.code", 2, [-2100, -864], {"jsCode": router_code()}),
        if_node("Tem Acesso aos Ativos?", "asset-access-branch", [-1870, -864], "asset_denied"),
        if_node("Consulta de Ativos?", "asset-domain-branch", [-1650, -700], "asset"),
        node("Responder Sem Acesso a Ativos", "asset-access-denied", "n8n-nodes-base.code", 2,
             [-1580, -1000], {"jsCode": "return [{json:{output:'Você não tem permissão para consultar a Central de Ativos.'}}];"}),
        ai, model, parser,
        node("Mesclar Consulta de Ativos", "asset-query-merge", "n8n-nodes-base.code", 2,
             [-1300, -1180], {"jsCode": ASSET_MERGE_CODE}),
        node("Consultar Ativos", "asset-query-http", "n8n-nodes-base.httpRequest", 4.5, [-1000, -1180], {
            "method": "POST", "url": "http://backend:8000/chatbot/assets-query", "sendBody": True,
            "specifyBody": "json", "jsonBody": ASSET_BODY, "options": {},
            "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
        }),
        node("Montar Resposta de Ativos", "asset-query-response", "n8n-nodes-base.code", 2,
             [-700, -1180], {"jsCode": ASSET_RESPONSE_CODE}),
    ]
    next(item for item in new_nodes if item["name"] == "Consultar Ativos")["credentials"] = credential
    result["nodes"].extend(new_nodes)
    # Abre espaço para os dois caminhos no canvas e preserva os nós antigos.
    for old in result["nodes"]:
        if old["name"] in by_name and old["name"] != "When chat message received":
            old["position"] = [old["position"][0] + 800, old["position"][1] + 260]
    c = result["connections"]
    c["When chat message received"]["main"] = [[connect("Roteamento da Consulta")]]
    c["Roteamento da Consulta"] = {"main": [[connect("Tem Acesso aos Ativos?")]]}
    c["Tem Acesso aos Ativos?"] = {"main": [[connect("Responder Sem Acesso a Ativos")], [connect("Consulta de Ativos?")]]}
    c["Consulta de Ativos?"] = {"main": [[connect("Interpretar Consulta de Ativos")], [connect("Buscar Estado da Conversa")]]}
    c["Google Gemini Ativos"] = {"ai_languageModel": [[{"node": "Interpretar Consulta de Ativos", "type": "ai_languageModel", "index": 0}]]}
    c["Estrutura da Consulta de Ativos"] = {"ai_outputParser": [[{"node": "Interpretar Consulta de Ativos", "type": "ai_outputParser", "index": 0}]]}
    c["Interpretar Consulta de Ativos"] = {"main": [[connect("Mesclar Consulta de Ativos")]]}
    c["Mesclar Consulta de Ativos"] = {"main": [[connect("Consultar Ativos")]]}
    c["Consultar Ativos"] = {"main": [[connect("Montar Resposta de Ativos")]]}

    return _religar_marco1(result)


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    source, destination = map(Path, sys.argv[1:])
    workflows = json.loads(source.read_text(encoding="utf-8"))
    if len(workflows) != 1:
        raise ValueError("Forneça a exportação de um único workflow.")
    destination.write_text(json.dumps([patch_workflow(workflows[0])], ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Workflow de ativos gravado em {destination}.")


if __name__ == "__main__":
    main()
