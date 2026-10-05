"""Confere os dois ramos novos antes de importar e publicar o workflow."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from add_domain_query_branches import GERADOS  # noqa: E402


def workflow(path):
    raw = json.load(open(path, encoding="utf-8"))
    return raw[0] if isinstance(raw, list) else raw


def targets(connections, name):
    return [[entry["node"] for entry in branch] for branch in connections[name]["main"]]


def main(before_path, after_path):
    before, after = workflow(before_path), workflow(after_path)
    original = {node["name"]: node for node in before["nodes"]}
    nodes = {node["name"]: node for node in after["nodes"]}
    assert before["id"] == after["id"]
    assert len(nodes) == len(after["nodes"])
    assert len({node["id"] for node in after["nodes"]}) == len(nodes)
    # Os nós que o script gera sao reconstruidos a cada aplicacao, de proposito:
    # e assim que uma correcao no codigo de mesclagem chega ao workflow. Quando o
    # "antes" ja e um workflow do marco 2, compara-los acusaria alteracao
    # legitima. O que esta checagem protege sao os nos ANTERIORES aos ramos.
    for name, node in original.items():
        if name in GERADOS:
            continue
        if name == "Responder Assunto Desconhecido":
            assert nodes[name]["parameters"]["jsCode"] != node["parameters"]["jsCode"]
            assert {**nodes[name], "parameters": {**nodes[name]["parameters"],
                                                  "jsCode": node["parameters"]["jsCode"]}} == node
            continue
        assert nodes[name] == node, f"Nó existente alterado: {name}"
    for name, connection in before["connections"].items():
        if name != "Assunto Desconhecido?":
            assert after["connections"][name] == connection, f"Conexão existente alterada: {name}"
    c = after["connections"]
    assert targets(c, "Assunto Desconhecido?") == [
        ["Responder Assunto Desconhecido"], ["Consulta de Custos?"],
    ]
    assert targets(c, "Consulta de Custos?") == [
        ["Interpretar Consulta de Custos"], ["Consulta de Preventivas?"],
    ]
    assert targets(c, "Consulta de Preventivas?") == [
        ["Interpretar Consulta de Preventivas"], ["Consulta de Ativos?"],
    ]
    for title, endpoint in (("Custos", "costs-query"), ("Preventivas", "preventive-query")):
        merge = "Mesclar Consulta de Custos" if title == "Custos" else "Mesclar Consulta Preventiva"
        sequence = [f"Interpretar Consulta de {title}", merge, f"Salvar Estado de {title}",
                    f"Consultar {title}", f"Montar Resposta de {title}"]
        for origin, destination in zip(sequence, sequence[1:]):
            assert targets(c, origin) == [[destination]]
        http = nodes[f"Consultar {title}"]
        assert http["parameters"]["url"] == f"http://backend:8000/chatbot/{endpoint}"
        assert http["credentials"] == original["Consultar Ativos"]["credentials"]
        mapped = nodes[f"Salvar Estado de {title}"]["parameters"]["columns"]["value"]
        assert mapped["domain"] == "={{ $('Roteamento da Consulta').first().json.domain }}"
        for field in ("session_id", "query_shape", "store_name", "praca", "year", "month"):
            assert field in mapped
    assert "contaRazao" in nodes["Mesclar Consulta de Custos"]["parameters"]["jsCode"]
    print("marco 2: topologia, credenciais, estado e nós anteriores OK")


if __name__ == "__main__":
    # Dois caminhos são obrigatórios: a verificação compara o workflow gerado
    # com o anterior para provar que nenhum nó existente foi perdido. Sem a
    # mensagem, chamar com um argumento só estourava um TypeError cru.
    if len(sys.argv) != 3:
        sys.exit(
            "uso: verificar_marco2.py ANTES.json DEPOIS.json\n"
            "  ANTES  = exportação do workflow sem os ramos de custos/preventiva\n"
            "  DEPOIS = workflow gerado por add_domain_query_branches.py"
        )
    main(*sys.argv[1:3])
