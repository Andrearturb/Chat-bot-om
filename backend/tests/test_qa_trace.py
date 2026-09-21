import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("API_KEY", "qa-test-api-key")

from fastapi import HTTPException
import pytest

from app.api.dependencies import verificar_api_key
from app.schemas.chatbot import ChatbotQueryRequest
from app.services.chatbot_query import ChatbotQueryError, validar_sql
from app.services.qa_trace import clear_qa_traces, get_qa_trace, register_qa_trace


def test_qa_trace_id_opcional():
    payload = ChatbotQueryRequest(sql="SELECT 1")
    assert payload.qa_trace_id is None


def test_request_sem_qa_trace_id_continua_funcionando():
    payload = ChatbotQueryRequest(sql="SELECT 1")
    assert payload.sql == "SELECT 1"


def test_trace_registra_sql_quando_id_existe():
    clear_qa_traces()

    register_qa_trace(
        trace_id="trace-1",
        sql="SELECT * FROM services",
        sql_validado="SELECT * FROM services",
        success=True,
        row_count=2,
        truncated=False,
        error=None,
    )

    trace = get_qa_trace("trace-1")
    assert trace is not None
    assert len(trace) == 1
    assert trace[0]["sql"] == "SELECT * FROM services"
    assert trace[0]["success"] is True


def test_multiplas_queries_no_mesmo_trace_ficam_registradas():
    clear_qa_traces()

    for item in [
        ("SELECT 1", "SELECT 1", True, 1, False, None),
        ("SELECT 2", "SELECT 2", False, 0, False, "falhou"),
    ]:
        register_qa_trace("trace-2", *item)

    trace = get_qa_trace("trace-2")
    assert len(trace) == 2
    assert trace[0]["sql"] == "SELECT 1"
    assert trace[1]["error"] == "falhou"


def test_endpoint_exige_api_key():
    with pytest.raises(HTTPException):
        verificar_api_key("chave-incorreta")


def test_trace_inexistente_retornando_none():
    clear_qa_traces()
    assert get_qa_trace("nao-existe") is None


def test_nenhuma_operacao_de_escrita_permitida():
    with pytest.raises(ChatbotQueryError):
        validar_sql("UPDATE services SET status = 'Em atendimento'")


def test_sql_validator_existente_continua_funcionando():
    assert validar_sql("SELECT COUNT(*) FROM services").strip().endswith(";") is False
