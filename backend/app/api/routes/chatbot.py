from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import verificar_api_key
from app.db.session import get_db
from app.schemas.chatbot import (
    ChatbotQueryRequest,
    ChatbotQueryResponse,
)
from app.schemas.structured_query import (
    StructuredQueryRequest,
    StructuredQueryResponse,
)
from app.services.chatbot_query import (
    ChatbotQueryError,
    executar_consulta_chatbot,
)
from app.services.qa_trace import get_qa_trace
from app.services.structured_query import (
    StructuredQueryError,
    execute_structured_query,
)


router = APIRouter(
    prefix="/chatbot",
    tags=["Chatbot"],
)


@router.post(
    "/query",
    response_model=ChatbotQueryResponse,
)
def executar_query(
    payload: ChatbotQueryRequest,
    db: Session = Depends(get_db),
):
    try:
        return executar_consulta_chatbot(
            db=db,
            sql=payload.sql,
            qa_trace_id=payload.qa_trace_id,
        )

    except ChatbotQueryError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Erro ao executar consulta no banco de dados.",
        ) from exc


@router.get(
    "/qa-traces/{trace_id}",
)
def listar_qa_trace(
    trace_id: str,
    _api_key_check: None = Depends(verificar_api_key),
):
    trace = get_qa_trace(trace_id)
    if trace is None:
        raise HTTPException(
            status_code=404,
            detail="Trace de QA não encontrado.",
        )
    return trace


@router.post(
    "/structured-query",
    response_model=StructuredQueryResponse,
)
def executar_structured_query(
    payload: StructuredQueryRequest,
    db: Session = Depends(get_db),
):
    try:
        return execute_structured_query(db=db, request=payload)
    except StructuredQueryError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Erro ao executar consulta estruturada.",
        ) from exc