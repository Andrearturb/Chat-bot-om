"""
/chatbot/query              — requer x-api-key (uso interno)
/chatbot/structured-query   — requer X-Internal-API-Key (n8n → backend)
/chatbot/qa-traces/{id}     — requer x-api-key
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import verificar_api_key, verificar_internal_api_key
from app.db.session import get_db
from app.schemas.chatbot import ChatbotQueryRequest, ChatbotQueryResponse
from app.schemas.structured_query import StructuredQueryRequest, StructuredQueryResponse
from app.services.chatbot_query import ChatbotQueryError, executar_consulta_chatbot
from app.services.qa_trace import get_qa_trace
from app.services.structured_query import StructuredQueryError, execute_structured_query

router = APIRouter(prefix="/chatbot", tags=["Chatbot"])


@router.post("/query", response_model=ChatbotQueryResponse,
             dependencies=[Depends(verificar_api_key)])
def executar_query(payload: ChatbotQueryRequest, db: Session = Depends(get_db)):
    try:
        return executar_consulta_chatbot(db=db, sql=payload.sql, qa_trace_id=payload.qa_trace_id)
    except ChatbotQueryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Erro ao executar consulta.") from exc


@router.get("/qa-traces/{trace_id}", dependencies=[Depends(verificar_api_key)])
def listar_qa_trace(trace_id: str):
    trace = get_qa_trace(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace não encontrado.")
    return trace


@router.post("/structured-query", response_model=StructuredQueryResponse,
             dependencies=[Depends(verificar_internal_api_key)])
def executar_structured_query(payload: StructuredQueryRequest, db: Session = Depends(get_db)):
    """Chamada server-to-server do n8n. Requer X-Internal-API-Key."""
    try:
        return execute_structured_query(db=db, request=payload)
    except StructuredQueryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Erro ao executar consulta estruturada.") from exc
