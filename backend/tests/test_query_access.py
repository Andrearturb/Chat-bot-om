"""Comprovante de consulta: assinatura, validade e domínios."""

import base64
import hashlib
import hmac
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
    # O instante real é capturado antes de substituir time.time; usar time.time()
    # dentro do lambda chamaria a própria substituta e recorreria sem fim.
    agora = time.time()
    monkeypatch.setattr(time, "time", lambda: agora + 181)

    assert verify_query_token(token, SESSAO, "ativos") is False


@pytest.mark.parametrize("token", ["", "sem-ponto", "a.b", None])
def test_comprovante_malformado_e_recusado(token):
    assert verify_query_token(token, SESSAO, "ativos") is False


def test_comprovante_antigo_sem_dominios_nao_autoriza():
    """Token do formato anterior não tem 'domains'; não pode valer por omissão."""
    from app.core.config import INTERNAL_API_KEY

    carga = {"session_id": SESSAO, "user_id": 7, "exp": int(time.time()) + 180}
    corpo = base64.urlsafe_b64encode(
        json.dumps(carga, separators=(",", ":")).encode()
    ).rstrip(b"=")
    assinatura = hmac.new(INTERNAL_API_KEY.encode(), corpo, hashlib.sha256).hexdigest()

    assert verify_query_token(f"{corpo.decode()}.{assinatura}", SESSAO, "ativos") is False
