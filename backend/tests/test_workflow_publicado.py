"""Os verificadores de workflow como regressão, não como ritual.

Os dois scripts em ``n8n/router/`` só valiam quando alguém lembrava de rodá-los.
Foi assim que o export commitado ficou com o roteador antigo enquanto
``route.js`` já tinha a correção: o repositório parou de reproduzir o que estava
no ar e nada acusou. Aqui eles rodam a cada ``pytest``.
"""

import subprocess
import sys
from pathlib import Path

import pytest


RAIZ = Path(__file__).resolve().parents[2]
PUBLICADO = RAIZ / "n8n" / "workflows" / "chat-om-publicado.json"
VERIFICADORES = RAIZ / "n8n" / "router"


def _rodar(script: str, *argumentos: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(VERIFICADORES / script), *argumentos],
        capture_output=True, text=True, cwd=str(RAIZ),
    )


def test_export_publicado_existe():
    """O default do domains.test.js aponta para este arquivo: sem ele, a suíte
    do frontend inteira morre em ENOENT num clone limpo."""
    assert PUBLICADO.is_file(), f"falta {PUBLICADO.relative_to(RAIZ)}"


def test_topologia_do_workflow_publicado():
    resultado = _rodar("verificar_fluxo.py", str(PUBLICADO))

    assert resultado.returncode == 0, resultado.stdout + resultado.stderr


def test_roteador_publicado_corresponde_ao_modulo():
    """O nó de roteamento é artefato gerado de route.js. Divergir significa que o
    repositório não reproduz o workflow em produção."""
    import json

    sys.path.insert(0, str(RAIZ / "n8n"))
    from add_asset_query_branch import router_code

    workflow = json.loads(PUBLICADO.read_text(encoding="utf-8"))[0]
    no = {item["name"]: item for item in workflow["nodes"]}["Roteamento da Consulta"]

    assert no["parameters"]["jsCode"].strip() == router_code().strip(), (
        "o workflow publicado divergiu de n8n/router/route.js; regere com "
        "add_asset_query_branch.py e depois add_domain_query_branches.py"
    )


def test_verificador_recusa_argumento_faltando():
    """Chamar sem o 'antes' estourava TypeError cru em vez de explicar."""
    resultado = _rodar("verificar_marco2.py", str(PUBLICADO))

    assert resultado.returncode != 0
    assert "uso:" in resultado.stdout + resultado.stderr


@pytest.mark.parametrize("script", ["verificar_fluxo.py", "verificar_marco2.py"])
def test_verificadores_sao_executaveis(script):
    """Guarda contra erro de sintaxe ou import quebrado nos próprios gates."""
    resultado = _rodar(script)

    # Sem argumentos devem explicar o uso, nunca estourar traceback.
    assert "Traceback" not in resultado.stderr, resultado.stderr
