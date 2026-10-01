"""
Lista de usuários: uma linha por pessoa.

Quando a conta de alguém é recriada no Keycloak ela ganha um novo ``subject`` e o app
cria um registro novo (de propósito: nunca vincula por e-mail). Os registros antigos
continuam no banco para a auditoria, mas a lista mostra só o mais recente.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.dates import utcnow
from app.models.auth import AppUser, UserSession
from tests.api_harness import SESSION_COOKIE, TestSession, fastapi_app, reset_database, seed_session

AGORA = utcnow()


@pytest.fixture(autouse=True)
def clean():
    reset_database()
    yield
    reset_database()


@pytest.fixture
def gestor() -> TestClient:
    token, _ = seed_session(["users.view"])
    client = TestClient(fastapi_app, raise_server_exceptions=False)
    client.cookies.set(SESSION_COOKIE, token)
    return client


def criar(email: str, nome: str, visto: datetime, perfis=("ANALISTA",)) -> int:
    db = TestSession()
    try:
        user = AppUser(email=email, display_name=nome, username=email.split("@")[0],
                       last_profiles=list(perfis), created_at=visto, last_seen_at=visto)
        db.add(user)
        db.commit()
        return user.id
    finally:
        db.close()


def abrir_sessao(user_id: int) -> None:
    db = TestSession()
    try:
        token = secrets.token_urlsafe(16)
        db.add(UserSession(
            user_id=user_id, session_token_hash=hashlib.sha256(token.encode()).hexdigest(),
            csrf_secret="x", created_at=AGORA, last_seen_at=AGORA,
            expires_at=AGORA + timedelta(hours=1), absolute_expires_at=AGORA + timedelta(hours=8),
            permissions=[], profiles=[], snapshot_refreshed_at=AGORA))
        db.commit()
    finally:
        db.close()


def linhas(client: TestClient) -> dict[str, dict]:
    return {u["email"]: u for u in client.get("/users").json()}


def test_conta_recriada_aparece_uma_vez_com_os_dados_mais_recentes(gestor):
    criar("ana@gentil.test", "Ana (antiga)", AGORA - timedelta(days=3), perfis=("CONVIDADO",))
    nova = criar("ana@gentil.test", "Ana Lima", AGORA - timedelta(hours=1), perfis=("GERENTE",))
    usuarios = [u for u in gestor.get("/users").json() if u["email"] == "ana@gentil.test"]
    assert len(usuarios) == 1
    assert usuarios[0]["id"] == nova
    assert usuarios[0]["display_name"] == "Ana Lima" and usuarios[0]["profile"] == "GERENTE"


def test_e_mail_com_maiusculas_conta_como_o_mesmo(gestor):
    criar("Bruno@Gentil.test", "Bruno A", AGORA - timedelta(days=2))
    criar("bruno@gentil.test", "Bruno B", AGORA - timedelta(days=1))
    assert len([u for u in gestor.get("/users").json() if u["email"].lower() == "bruno@gentil.test"]) == 1


def test_sessao_ativa_na_conta_antiga_continua_aparecendo(gestor):
    antiga = criar("carla@gentil.test", "Carla", AGORA - timedelta(days=2))
    criar("carla@gentil.test", "Carla", AGORA - timedelta(hours=2))
    abrir_sessao(antiga)
    assert linhas(gestor)["carla@gentil.test"]["active_session"] is True


def test_pessoas_diferentes_nao_se_misturam(gestor):
    criar("diego@gentil.test", "Diego", AGORA)
    criar("eva@gentil.test", "Eva", AGORA)
    assert {"diego@gentil.test", "eva@gentil.test"} <= set(linhas(gestor))


def test_registros_sem_e_mail_nunca_sao_agrupados(gestor):
    criar("", "Sem e-mail 1", AGORA)
    criar("", "Sem e-mail 2", AGORA)
    nomes = [u["display_name"] for u in gestor.get("/users").json() if not u["email"]]
    assert sorted(nomes) == ["Sem e-mail 1", "Sem e-mail 2"]
