"""Confere a topologia exigida pelo marco 1 num workflow patchado."""

import json
import sys

destino = sys.argv[1]
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

for nome, esperado in (("Acesso Negado?", "sem_acesso"),
                       ("Assunto Desconhecido?", "desconhecido"),
                       ("Consulta de Ativos?", "ativos")):
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

# Encadeamento dos tres IF, na ordem: acesso, assunto, dominio.
ESPERADO = {
    "When chat message received": ["Buscar Estado da Conversa"],
    "Buscar Estado da Conversa": ["Roteamento da Consulta"],
    "Roteamento da Consulta": ["Acesso Negado?"],
    "Acesso Negado?": ["Responder Sem Acesso", "Assunto Desconhecido?"],
    "Assunto Desconhecido?": ["Responder Assunto Desconhecido", "Consulta de Ativos?"],
    "Consulta de Ativos?": ["Interpretar Consulta de Ativos", "Interpretar Estado da Consulta"],
}
for origem, destinos in ESPERADO.items():
    if alvos(origem) != destinos:
        falhas.append(f"{origem} deveria sair para {destinos}, sai para {alvos(origem)}")

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
for no_salvar in ("Salvar Estado da Conversa", "Salvar Estado de Ativos"):
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
