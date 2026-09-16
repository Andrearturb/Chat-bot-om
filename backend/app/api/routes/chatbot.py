from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.chatbot import (
    ChatbotQueryRequest,
    ChatbotQueryResponse,
)
from app.services.chatbot_query import (
    ChatbotQueryError,
    executar_consulta_chatbot,
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