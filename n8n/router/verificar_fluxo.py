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


if "Google Gemini Chat Model1" in nos:
    falhas.append("o no Gemini duplicado ainda existe")

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

for nome, esperado in (("Acesso Negado?", "sem_acesso"), ("Consulta de Ativos?", "ativos")):
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

salvar = nos.get("Salvar Estado da Conversa", {})
mapeadas = salvar.get("parameters", {}).get("columns", {}).get("value", {})
if "domain" not in mapeadas:
    falhas.append("Salvar Estado da Conversa nao grava domain")

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
