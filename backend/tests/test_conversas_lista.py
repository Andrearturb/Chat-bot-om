"""
Lista de conversas do assistente (GET /assistant/conversations).

O painel "Conversas" precisa de id, título, datas e o número de mensagens de cada conversa.
Antes, a lista não trazia o número de mensagens e a tela quebrava ao abrir o histórico
assim que existia uma conversa salva.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.dates import utcnow
from app.models.auth import AppUser, AssistantConversation, AssistantMessage
from tests.api_harness import SESSION_COOKIE, TestSession, fastapi_app, reset_database, seed_session


@pytest.fixture(autouse=True)
def clean():
    reset_database()
    yield
    reset_database()


@pytest.fixture
def cliente() -> TestClient:
    token, _ = seed_session(["assistant.use", "assistant.history"])
    client = TestClient(fastapi_app, raise_server_exceptions=False)
    client.cookies.set(SESSION_COOKIE, token)
    return client


def criar_conversa(db, user_id: int, conversa_id: str, mensagens: int, atualizada: datetime, *,
                   arquivada: bool = False) -> None:
    db.add(AssistantConversation(id=conversa_id, user_id=user_id, n8n_session_id=conversa_id, title=f"Conversa {conversa_id}",
                                 created_at=atualizada, updated_at=atualizada,
                                 archived_at=atualizada if arquivada else None))
    for indice in range(mensagens):
        db.add(AssistantMessage(id=f"{conversa_id}-m{indice}", conversation_id=conversa_id,
                                role="user" if indice % 2 == 0 else "assistant", content="texto",
                                created_at=atualizada))


def test_lista_traz_o_numero_de_mensagens_de_cada_conversa(cliente):
    db = TestSession()
    user = db.query(AppUser).filter_by(email="api@test.com").one()
    agora = utcnow()
    criar_conversa(db, user.id, "c1", 2, agora - timedelta(hours=2))
    criar_conversa(db, user.id, "c2", 5, agora - timedelta(hours=1))
    criar_conversa(db, user.id, "c3", 0, agora - timedelta(minutes=5))
    db.commit()
    db.close()

    lista = cliente.get("/assistant/conversations").json()

    assert [(c["id"], c["message_count"]) for c in lista] == [("c3", 0), ("c2", 5), ("c1", 2)]   # mais recente primeiro
    assert {"id", "title", "created_at", "updated_at", "message_count"} <= set(lista[0])


def test_conversa_arquivada_e_de_outra_pessoa_nao_entram_na_lista(cliente):
    db = TestSession()
    user = db.query(AppUser).filter_by(email="api@test.com").one()
    outra = AppUser(email="outra@test.com", display_name="Outra")
    db.add(outra)
    db.flush()
    agora = utcnow()
    criar_conversa(db, user.id, "minha", 1, agora)
    criar_conversa(db, user.id, "arquivada", 1, agora, arquivada=True)
    criar_conversa(db, outra.id, "alheia", 3, agora)
    db.commit()
    db.close()

    assert [c["id"] for c in cliente.get("/assistant/conversations").json()] == ["minha"]


def test_lista_vazia(cliente):
    assert cliente.get("/assistant/conversations").json() == []
