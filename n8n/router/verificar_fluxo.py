"""Confere a topologia exigida pelo marco 1 num workflow patchado."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from add_asset_query_branch import router_code  # noqa: E402

if len(sys.argv) < 2:
    sys.exit("uso: verificar_fluxo.py WORKFLOW.json [--sem-roteador]\n"
             "  --sem-roteador  pula a comparacao com route.js, para inspecionar\n"
             "                  um export historico sem alarme falso")
destino = sys.argv[1]
comparar_roteador = "--sem-roteador" not in sys.argv[2:]
workflow = json.load(open(destino, encoding="utf-8"))[0]
nos = {n["name"]: n for n in workflow["nodes"]}
conexoes = workflow["connections"]

falhas = []


def alvos(nome):
    return [c["node"] for b in conexoes.get(nome, {}).get("main", [[]]) for c in (b or [])]


# Os dois nos Gemini de "Interpretar Estado da Consulta" nao sao duplicados: o
# Model1 e o modelo principal (ai_languageModel indice 0) e o Model e o fallback
# (indice 1), porque o no tem needsFallback=True. Remover o do indice 0 derruba a
# cadeia com "A Model sub-node must be connected and enabled" - foi o que
# aconteceu, e e por isso que esta checagem existe.
MODELOS = {
    "Google Gemini Chat Model1": ("Interpretar Estado da Consulta", 0),
    "Google Gemini Chat Model": ("Interpretar Estado da Consulta", 1),
    "Google Gemini Ativos": ("Interpretar Consulta de Ativos", 0),
}
for modelo, (destino, indice) in MODELOS.items():
    if modelo not in nos:
        falhas.append(f"falta o no de modelo {modelo}")
        continue
    if nos[modelo].get("disabled"):
        falhas.append(f"{modelo} esta desabilitado")
    ligacoes = [
        (c["node"], c.get("index"))
        for b in conexoes.get(modelo, {}).get("ai_languageModel", [[]])
        for c in (b or [])
    ]
    if (destino, indice) not in ligacoes:
        falhas.append(f"{modelo} deveria alimentar {destino} no indice {indice}; liga {ligacoes}")

if alvos("When chat message received") != ["Buscar Estado da Conversa"]:
    falhas.append(f"o gatilho deveria ir para Buscar Estado da Conversa, vai para {alvos('When chat message received')}")

if alvos("Buscar Estado da Conversa") != ["Roteamento da Consulta"]:
    falhas.append(f"Buscar Estado deveria ir para o roteador, vai para {alvos('Buscar Estado da Conversa')}")

js = nos.get("Roteamento da Consulta", {}).get("parameters", {}).get("jsCode", "")
for exigido in ("chamados_preventiva", "allowedDomains", "estadoPreservado",
                "CAMPOS_COMPARTILHADOS", "followUpHint"):
    if exigido not in js:
        falhas.append(f"jsCode do roteador sem {exigido}")
if "module.exports" in js:
    falhas.append("module.exports vazou para o jsCode")

# O no do roteador e artefato gerado de n8n/router/route.js. Sem comparar o
# conteudo inteiro, o repositorio deixa de reproduzir o que esta no ar: foi o que
# aconteceu quando o export commitado ficou com a regex antiga de custo enquanto
# route.js ja tinha a nova, e cinco verificacoes de substring passaram verdes.
if comparar_roteador and js.strip() != router_code().strip():
    falhas.append(
        "o jsCode do no de roteamento divergiu de n8n/router/route.js. "
        "Regere com add_asset_query_branch.py (e depois add_domain_query_branches.py), "
        "ou use --sem-roteador se o arquivo for um export historico."
    )

CONDICOES = [
    ("Acesso Negado?", "sem_acesso"),
    ("Assunto Desconhecido?", "desconhecido"),
    ("Consulta de Ativos?", "ativos"),
    # A partir do marco 2; opcionais para o verificador servir aos dois.
    ("Consulta de Custos?", "custos"),
    ("Consulta de Preventivas?", "chamados_preventiva"),
]
for nome, esperado in [(n, v) for n, v in CONDICOES if n in nos or n.endswith(("Negado?", "Desconhecido?", "Ativos?"))]:
    no = nos.get(nome)
    if not no:
        falhas.append(f"falta o no {nome}")
        continue
    cond = no["parameters"]["conditions"]["conditions"][0]
    if cond["leftValue"] != "={{ $json.domain }}" or cond["rightValue"] != esperado:
        falhas.append(f"{nome} testa {cond['leftValue']} == {cond['rightValue']}")

if "Responder Sem Acesso" not in nos:
    falhas.append("falta o no Responder Sem Acesso")
elif "deniedDomain" not in nos["Responder Sem Acesso"]["parameters"].get("jsCode", ""):
    falhas.append("Responder Sem Acesso nao nomeia o dominio recusado")

if "Responder Assunto Desconhecido" not in nos:
    falhas.append("falta o no Responder Assunto Desconhecido: a rota desconhecida "
                  "cairia no ramo de chamados e seria respondida como corretiva")

# Cabeca fixa do fluxo: estado, roteador, acesso, assunto.
ESPERADO = {
    "When chat message received": ["Buscar Estado da Conversa"],
    "Buscar Estado da Conversa": ["Roteamento da Consulta"],
    "Roteamento da Consulta": ["Acesso Negado?"],
    "Acesso Negado?": ["Responder Sem Acesso", "Assunto Desconhecido?"],
}
for origem, destinos in ESPERADO.items():
    if alvos(origem) != destinos:
        falhas.append(f"{origem} deveria sair para {destinos}, sai para {alvos(origem)}")

# Cascata de dominio: cada IF presente trata o seu e passa o resto adiante, e o
# ultimo cai na corretiva. A ordem e fixa, mas os IF do meio sao opcionais -
# custos e preventiva existem a partir do marco 2. A saida falsa do ultimo IF
# tem de ser Interpretar Estado da Consulta, nunca Buscar Estado da Conversa:
# apontar de volta para a leitura do estado fecha o ciclo que pendura o fluxo.
CASCATA = [
    ("Consulta de Custos?", "Interpretar Consulta de Custos"),
    ("Consulta de Preventivas?", "Interpretar Consulta de Preventivas"),
    ("Consulta de Ativos?", "Interpretar Consulta de Ativos"),
]
presentes = [(no, ramo) for no, ramo in CASCATA if no in nos]
if not presentes:
    falhas.append("nenhum IF de dominio no fluxo")
elif alvos("Assunto Desconhecido?") != ["Responder Assunto Desconhecido", presentes[0][0]]:
    falhas.append(
        f"Assunto Desconhecido? deveria entrar na cascata por {presentes[0][0]}, "
        f"sai para {alvos('Assunto Desconhecido?')}"
    )
for indice, (no_if, ramo) in enumerate(presentes):
    seguinte = presentes[indice + 1][0] if indice + 1 < len(presentes) else "Interpretar Estado da Consulta"
    if alvos(no_if) != [ramo, seguinte]:
        falhas.append(f"{no_if} deveria sair para ['{ramo}', '{seguinte}'], sai para {alvos(no_if)}")

# Nenhum no pode reentrar em Buscar Estado da Conversa: ela e o primeiro no, e
# uma segunda entrada fecha o ciclo Buscar -> Roteamento -> IF -> Buscar, que
# pendura a execucao sem erro nenhum no log.
entradas = [nome for nome in conexoes if "Buscar Estado da Conversa" in alvos(nome)]
if entradas != ["When chat message received"]:
    falhas.append(f"Buscar Estado da Conversa recebe de {entradas}; so o gatilho pode alimenta-la")

ROTEADOR_DOMAIN = "={{ $('Roteamento da Consulta').first().json.domain }}"

# domain tem de vir por referencia ao roteador. No Salvar, $json e a saida do
# Mesclar, que nao carrega domain: "={{ $json.domain }}" grava vazio e o turno
# seguinte perde o contexto por nao ter lastDomain.
SALVAR = ["Salvar Estado da Conversa", "Salvar Estado de Ativos"]
# Cada dominio da cascata precisa do seu no de salvar, senao o acompanhamento
# daquele dominio perde o contexto no turno seguinte.
for no_if, no_salvar in (("Consulta de Custos?", "Salvar Estado de Custos"),
                         ("Consulta de Preventivas?", "Salvar Estado de Preventivas")):
    if no_if in nos:
        SALVAR.append(no_salvar)
for no_salvar in SALVAR:
    if no_salvar not in nos:
        falhas.append(f"falta o no {no_salvar}: sem ele o acompanhamento perde o contexto")
        continue
    mapeadas = nos[no_salvar]["parameters"].get("columns", {}).get("value", {})
    if mapeadas.get("domain") != ROTEADOR_DOMAIN:
        falhas.append(f"{no_salvar} grava domain como {mapeadas.get('domain')!r}, nao do roteador")

if "Mesclar Consulta de Ativos" in nos:
    codigo = nos["Mesclar Consulta de Ativos"]["parameters"]["jsCode"]
    if "JSON.parse(previous.asset_type)" not in codigo:
        falhas.append("Mesclar Consulta de Ativos nao reidrata asset_types do texto persistido")

if alvos("Mesclar Consulta de Ativos") != ["Salvar Estado de Ativos"]:
    falhas.append(f"Mesclar Consulta de Ativos deveria salvar antes de consultar, sai para {alvos('Mesclar Consulta de Ativos')}")
if alvos("Salvar Estado de Ativos") != ["Consultar Ativos"]:
    falhas.append(f"Salvar Estado de Ativos deveria ir para Consultar Ativos, sai para {alvos('Salvar Estado de Ativos')}")

for ramo, no_merge in (("chamados", "Mesclar Estado da Consulta"), ("ativos", "Mesclar Consulta de Ativos")):
    codigo = nos.get(no_merge, {}).get("parameters", {}).get("jsCode", "")
    if "estadoPreservado" not in codigo:
        falhas.append(f"{no_merge} ({ramo}) nao usa estadoPreservado")

# Nenhum no pode referenciar campos que o backend deixou de enviar.
for nome, no in nos.items():
    blob = json.dumps(no, ensure_ascii=False)
    for antigo in ("assetQueryState", "assetFollowUpHint", "assetAccessToken", "hadAssetContext"):
        if antigo in blob:
            falhas.append(f"{nome} ainda referencia {antigo}")

if falhas:
    print("FALHOU:")
    for f in falhas:
        print("  -", f)
    sys.exit(1)
print("topologia OK")
