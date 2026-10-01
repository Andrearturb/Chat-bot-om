"""
Gateway do Assistente IA.
React → POST /assistant/chat → FastAPI → n8n → FastAPI → React
O frontend NUNCA chama o n8n diretamente.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_permission
from app.core.dates import iso_utc
from app.core.config import N8N_CHAT_WEBHOOK_URL, N8N_GATEWAY_TOKEN
from app.db.session import get_db
from app.models.auth import AiUsage, AppUser, AssistantConversation, AssistantMessage
from app.services.auth import check_ai_rate_limit, record_security_event

router = APIRouter(prefix="/assistant", tags=["Assistant"])
logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    response_time: float | None = None
    created_at: str


class ChatResponse(BaseModel):
    conversation_id: str
    message: MessageOut
    ai_usage: dict


class ConversationListItem(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str


def _call_n8n(session_id: str, message: str) -> str:
    if not N8N_CHAT_WEBHOOK_URL:
        raise HTTPException(status_code=503, detail="Assistente não configurado.")
    headers = {"Content-Type": "application/json"}
    if N8N_GATEWAY_TOKEN:
        headers["Authorization"] = f"Bearer {N8N_GATEWAY_TOKEN}"
    with httpx.Client(timeout=120.0) as client:
        resp = client.post(N8N_CHAT_WEBHOOK_URL,
                           json={"action": "sendMessage", "sessionId": session_id, "chatInput": message},
                           headers=headers)
        resp.raise_for_status()
    data = resp.json()
    return (data.get("output") or data.get("text") or data.get("response") or
            data.get("message") or str(data))


def _create_title(content: str) -> str:
    n = content.replace("\n", " ").strip()
    return (n[:45] + "...") if len(n) > 48 else (n or "Nova conversa")


@router.post("/chat", response_model=ChatResponse,
             dependencies=[Depends(require_permission("assistant.use"))])
def chat(payload: ChatRequest, user: AppUser = Depends(get_current_user),
         db: Session = Depends(get_db)) -> ChatResponse:
    content = payload.message.strip()
    if not content:
        raise HTTPException(status_code=422, detail="Mensagem não pode ser vazia.")

    rate = check_ai_rate_limit(db, user)
    if not rate["allowed"]:
        reason = rate["reason"]
        record_security_event(db, event_type="AI_RATE_LIMIT" if reason == "per_minute_limit" else "AI_DAILY_LIMIT",
                              severity="low", user_id=user.id, metadata={"reason": reason})
        db.commit()
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail={
            "error": "quota_exceeded", "reason": reason, "resets_at": rate["resets_at"],
            "message": ("Limite por minuto atingido." if reason == "per_minute_limit"
                        else "Limite diário do assistente atingido."),
        })

    now = datetime.utcnow()
    if payload.conversation_id:
        conversation = db.scalar(select(AssistantConversation).where(
            AssistantConversation.id == payload.conversation_id,
            AssistantConversation.user_id == user.id))
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    else:
        conversation = AssistantConversation(
            id=str(uuid.uuid4()), user_id=user.id, n8n_session_id=str(uuid.uuid4()),
            title=_create_title(content), created_at=now, updated_at=now)
        db.add(conversation)
        db.flush()

    user_msg = AssistantMessage(id=str(uuid.uuid4()), conversation_id=conversation.id,
                                role="user", content=content, created_at=now)
    db.add(user_msg)

    request_id = str(uuid.uuid4())
    ai_record = AiUsage(user_id=user.id, conversation_id=conversation.id,
                        request_id=request_id, status="pending", created_at=now,
                        prompt_chars=len(content))
    db.add(ai_record)
    db.flush()
    db.commit()

    start_ms = time.monotonic()
    assistant_text = ""
    error_code = None

    try:
        assistant_text = _call_n8n(conversation.n8n_session_id, content)
    except httpx.HTTPStatusError as exc:
        error_code = f"HTTP_{exc.response.status_code}"
        raise HTTPException(status_code=502, detail="O assistente encontrou um problema.") from exc
    except httpx.RequestError as exc:
        error_code = "NETWORK_ERROR"
        raise HTTPException(status_code=503, detail="O assistente está temporariamente indisponível.") from exc
    finally:
        elapsed_ms = int((time.monotonic() - start_ms) * 1000)
        ai_record.completed_at = datetime.utcnow()
        ai_record.duration_ms = elapsed_ms
        ai_record.status = "error" if error_code else "success"
        if error_code:
            ai_record.error_code = error_code
        if assistant_text:
            ai_record.response_chars = len(assistant_text)
        db.commit()

    assistant_msg = AssistantMessage(
        id=str(uuid.uuid4()), conversation_id=conversation.id,
        role="assistant", content=assistant_text,
        response_time=round(time.monotonic() - start_ms, 2),
        created_at=datetime.utcnow())
    db.add(assistant_msg)
    conversation.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(assistant_msg)

    updated_rate = check_ai_rate_limit(db, user)
    return ChatResponse(
        conversation_id=conversation.id,
        message=MessageOut(id=assistant_msg.id, role=assistant_msg.role, content=assistant_msg.content,
                           response_time=assistant_msg.response_time,
                           created_at=iso_utc(assistant_msg.created_at)),
        ai_usage={"used_today": updated_rate["used_today"], "daily_limit": updated_rate["daily_limit"],
                  "remaining": max(0, updated_rate["daily_limit"] - updated_rate["used_today"]),
                  "resets_at": updated_rate["resets_at"]},
    )


@router.get("/conversations", response_model=list[ConversationListItem],
            dependencies=[Depends(require_permission("assistant.history"))])
def list_conversations(user: AppUser = Depends(get_current_user), db: Session = Depends(get_db)):
    convs = db.scalars(select(AssistantConversation).where(
        AssistantConversation.user_id == user.id,
        AssistantConversation.archived_at.is_(None))
        .order_by(AssistantConversation.updated_at.desc()).limit(100)).all()
    return [ConversationListItem(id=c.id, title=c.title,
                                 created_at=iso_utc(c.created_at),
                                 updated_at=iso_utc(c.updated_at)) for c in convs]


@router.get("/conversations/{conversation_id}",
            dependencies=[Depends(require_permission("assistant.history"))])
def get_conversation(conversation_id: str, user: AppUser = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    conv = db.scalar(select(AssistantConversation).where(
        AssistantConversation.id == conversation_id,
        AssistantConversation.user_id == user.id))
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    msgs = db.scalars(select(AssistantMessage).where(
        AssistantMessage.conversation_id == conversation_id)
        .order_by(AssistantMessage.created_at.asc())).all()
    return {"id": conv.id, "title": conv.title, "created_at": iso_utc(conv.created_at),
            "updated_at": iso_utc(conv.updated_at),
            "messages": [{"id": m.id, "role": m.role, "content": m.content,
                          "response_time": m.response_time, "created_at": iso_utc(m.created_at)}
                         for m in msgs]}


@router.delete("/conversations/{conversation_id}", status_code=204,
               dependencies=[Depends(require_permission("assistant.history"))])
def delete_conversation(conversation_id: str, user: AppUser = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    conv = db.scalar(select(AssistantConversation).where(
        AssistantConversation.id == conversation_id,
        AssistantConversation.user_id == user.id))
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    conv.archived_at = datetime.utcnow()
    db.commit()
