"""
Gestão de usuários, sincronização Keycloak ↔ app, pré-provisionamento DEV,
login/logout OIDC — SQLite em memória + Keycloak Admin API simulada.

Reaproveita o harness de ``test_api_security`` (mesmo engine e mesmo app),
evitando dois engines de teste concorrentes no mesmo processo.
"""

from __future__ import annotations

import json
import uuid
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from tests.test_api_security import SESSION_COOKIE, _TestSession, _test_engine, fastapi_app  # noqa: F401

import app.api.routes.auth as auth_routes
import app.services.auth as auth_service
from app.db.base import Base
from app.models.auth import (
    AppUser,
    AuditLog,
    OidcIdentity,
    Permission,
    Profile,
    UserPermissionOverride,
    UserSession,
)
from app.services.auth import create_session, resolve_or_create_user, seed_profiles_and_permissions
from app.services.keycloak_admin import IdentityAdminError, IdentityUser, get_identity_admin
from app.services.user_admin import (
    active_admin_ids,
    provision_dev_users,
    username_from_email,
    validate_display_name,
    UserAdminError,
)

TEMP_PASSWORD = "Tmp#Senha-9281"


# ─── Keycloak Admin API simulada ──────────────────────────────────────────────

class FakeIdentityAdmin:
    def __init__(self, *, smtp: bool = False, configured: bool = True) -> None:
        self.accounts: dict[str, dict] = {}
        self.passwords: dict[str, dict] = {}
        self.calls: list[tuple] = []
        self.smtp = smtp
        self.configured = configured

    # helpers
    def seed(self, username: str, email: str, first: str = "Nome", last: str = "Teste", enabled: bool = True) -> str:
        account_id = str(uuid.uuid4())
        self.accounts[account_id] = {
            "id": account_id, "username": username, "email": email,
            "firstName": first, "lastName": last, "enabled": enabled, "requiredActions": [],
        }
        return account_id

    def _user(self, rep: dict) -> IdentityUser:
        return IdentityUser.from_representation(rep)

    # interface
    def is_configured(self) -> bool:
        return self.configured

    def smtp_configured(self) -> bool:
        return self.smtp

    def find_by_username(self, username):
        self.calls.append(("find_by_username", username))
        return next((self._user(a) for a in self.accounts.values() if a["username"] == username.lower()), None)

    def find_by_email(self, email):
        self.calls.append(("find_by_email", email))
        return next((self._user(a) for a in self.accounts.values() if (a["email"] or "").lower() == email.lower()), None)

    def get_user(self, user_id):
        rep = self.accounts.get(user_id)
        return self._user(rep) if rep else None

    def create_user(self, *, username, email, first_name, last_name, enabled=True,
                    temporary_password=None, required_actions=None):
        self.calls.append(("create_user", username))
        if any(a["username"] == username for a in self.accounts.values()):
            raise IdentityAdminError("Este nome de usuário já está em uso no provedor de identidade.", status_code=409)
        account_id = self.seed(username, email, first_name, last_name, enabled)
        self.accounts[account_id]["requiredActions"] = list(required_actions or [])
        if temporary_password:
            self.passwords[account_id] = {"value": temporary_password, "temporary": True}
        return account_id

    def update_user(self, user_id, *, first_name=None, last_name=None, enabled=None):
        self.calls.append(("update_user", user_id, enabled))
        rep = self.accounts[user_id]
        if first_name is not None:
            rep["firstName"] = first_name
        if last_name is not None:
            rep["lastName"] = last_name
        if enabled is not None:
            rep["enabled"] = enabled

    def set_temporary_password(self, user_id, password):
        self.calls.append(("set_temporary_password", user_id))
        self.passwords[user_id] = {"value": password, "temporary": True}

    def send_update_password_email(self, user_id, *, redirect_client_id=None):
        self.calls.append(("send_update_password_email", user_id))

    def logout_user(self, user_id):
        self.calls.append(("logout_user", user_id))

    def delete_user(self, user_id):
        self.calls.append(("delete_user", user_id))
        self.accounts.pop(user_id, None)
        self.passwords.pop(user_id, None)


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(bind=_test_engine)
    Base.metadata.create_all(bind=_test_engine)
    db = _TestSession()
    seed_profiles_and_permissions(db)
    db.close()
    yield
    fastapi_app.dependency_overrides.pop(get_identity_admin, None)
    Base.metadata.drop_all(bind=_test_engine)


@pytest.fixture
def idp():
    fake = FakeIdentityAdmin()
    fastapi_app.dependency_overrides[get_identity_admin] = lambda: fake
    return fake


def _profile(db, name):
    return db.scalar(select(Profile).where(Profile.name == name))


def _make_user(email, profile_name="ANALISTA", *, status="active", username=None, subject=None):
    db = _TestSession()
    user = AppUser(email=email, display_name=email.split("@")[0].replace(".", " ").title() + " Teste",
                   username=username, profile_id=_profile(db, profile_name).id if profile_name else None,
                   status=status)
    db.add(user)
    db.flush()
    if subject:
        db.add(OidcIdentity(user_id=user.id, issuer=auth_service.oidc_issuer(), subject=subject, email_at_link=email))
    db.commit()
    user_id = user.id
    db.close()
    return user_id


def _client_for(user_id):
    db = _TestSession()
    token = create_session(db, user_id)
    csrf = db.scalar(select(UserSession).where(UserSession.user_id == user_id).order_by(UserSession.id.desc())).csrf_secret
    db.close()
    client = TestClient(fastapi_app, raise_server_exceptions=False)
    client.__enter__()
    client.cookies.set(SESSION_COOKIE, token)
    client.headers.update({"X-CSRF-Token": csrf})
    return client


@pytest.fixture
def admin(idp):
    user_id = _make_user("chefe@empresa.com", "ADMINISTRADOR", username="chefe", subject=idp.seed("chefe", "chefe@empresa.com"))
    client = _client_for(user_id)
    client.user_id = user_id
    yield client
    client.__exit__(None, None, None)


@pytest.fixture
def analyst(idp):
    user_id = _make_user("ana@empresa.com", "ANALISTA", username="ana", subject=idp.seed("ana", "ana@empresa.com"))
    client = _client_for(user_id)
    client.user_id = user_id
    yield client
    client.__exit__(None, None, None)


def _new_user_payload(**overrides):
    payload = {
        "display_name": "Maria Oliveira",
        "email": "maria.oliveira@empresa.com",
        "username": "maria.oliveira",
        "profile": "GERENTE",
        "status": "active",
        "password_mode": "temporary",
        "temporary_password": TEMP_PASSWORD,
    }
    payload.update(overrides)
    return payload


# ─── 1-2. Acesso administrativo ───────────────────────────────────────────────

class TestAdminAccess:
    def test_admin_lista_usuarios(self, admin, analyst):
        r = admin.get("/users")
        assert r.status_code == 200
        emails = {u["email"] for u in r.json()}
        assert {"chefe@empresa.com", "ana@empresa.com"} <= emails
        me = next(u for u in r.json() if u["email"] == "chefe@empresa.com")
        assert me["is_self"] is True and me["identity_linked"] is True and me["username"] == "chefe"

    def test_busca_por_nome_email_usuario(self, admin, analyst):
        assert [u["email"] for u in admin.get("/users", params={"q": "ana@"}).json()] == ["ana@empresa.com"]
        assert [u["username"] for u in admin.get("/users", params={"q": "chef"}).json()] == ["chefe"]

    @pytest.mark.parametrize("method,path,body", [
        ("get", "/users", None),
        ("get", "/users/capabilities", None),
        ("post", "/users", _new_user_payload()),
        ("patch", "/users/1", {"profile": "ADMINISTRADOR"}),
        ("post", "/users/1/deactivate", {}),
        ("post", "/users/1/activate", {}),
        ("post", "/users/1/reset-password", {"temporary_password": TEMP_PASSWORD}),
        ("post", "/users/1/password-email", {}),
    ])
    def test_analista_recebe_403(self, analyst, idp, method, path, body):
        kwargs = {"json": body} if body is not None else {}
        r = getattr(analyst, method)(path, **kwargs)
        assert r.status_code == 403
        assert not any(call[0] in ("create_user", "update_user", "set_temporary_password") for call in idp.calls)

    def test_override_allow_nao_transforma_analista_em_admin(self, analyst):
        db = _TestSession()
        perm = db.scalar(select(Permission).where(Permission.code == "users.manage"))
        db.add(UserPermissionOverride(user_id=analyst.user_id, permission_id=perm.id, effect="allow"))
        db.commit(); db.close()
        assert analyst.get("/users").status_code == 403

    def test_sem_sessao_401(self, idp):
        with TestClient(fastapi_app, raise_server_exceptions=False) as c:
            assert c.get("/users").status_code == 401


# ─── 3-6. Cadastro, perfil, identidade e idempotência ─────────────────────────

class TestCreateUser:
    def test_cadastro_cria_no_keycloak_e_no_app(self, admin, idp):
        r = admin.post("/users", json=_new_user_payload())
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["user"]["email"] == "maria.oliveira@empresa.com"
        assert body["user"]["status"] == "active"

        account = idp.find_by_username("maria.oliveira")
        assert account is not None and account.enabled is True
        assert account.email == "maria.oliveira@empresa.com"
        assert account.first_name == "Maria" and account.last_name == "Oliveira"
        assert idp.passwords[account.id] == {"value": TEMP_PASSWORD, "temporary": True}

        db = _TestSession()
        user = db.scalar(select(AppUser).where(AppUser.email == "maria.oliveira@empresa.com"))
        assert user.username == "maria.oliveira" and user.display_name == "Maria Oliveira"
        db.close()

    def test_usuario_criado_recebe_perfil_correto(self, admin, idp):
        r = admin.post("/users", json=_new_user_payload(profile="DIRETOR"))
        assert r.status_code == 201
        assert r.json()["user"]["profile"] == "DIRETOR"
        db = _TestSession()
        user = db.scalar(select(AppUser).where(AppUser.email == "maria.oliveira@empresa.com"))
        assert db.get(Profile, user.profile_id).name == "DIRETOR"
        db.close()

    def test_oidc_identity_criada_com_issuer_e_subject(self, admin, idp):
        admin.post("/users", json=_new_user_payload())
        account = idp.find_by_username("maria.oliveira")
        db = _TestSession()
        user = db.scalar(select(AppUser).where(AppUser.email == "maria.oliveira@empresa.com"))
        identity = db.scalar(select(OidcIdentity).where(OidcIdentity.user_id == user.id))
        assert identity.subject == account.id
        assert identity.issuer == auth_service.oidc_issuer()
        assert identity.email_at_link == "maria.oliveira@empresa.com"
        db.close()

    def test_repetir_cadastro_nao_duplica(self, admin, idp):
        assert admin.post("/users", json=_new_user_payload()).status_code == 201
        r = admin.post("/users", json=_new_user_payload())
        assert r.status_code == 409
        assert r.json()["code"] == "user_exists"
        db = _TestSession()
        maria = db.scalars(select(AppUser).where(AppUser.email == "maria.oliveira@empresa.com")).all()
        assert len(maria) == 1
        assert db.scalar(select(func.count(OidcIdentity.id)).where(OidcIdentity.user_id == maria[0].id)) == 1
        db.close()
        assert sum(1 for a in idp.accounts.values() if a["username"] == "maria.oliveira") == 1

    def test_conta_orfa_no_keycloak_e_adotada_sem_duplicar(self, admin, idp):
        orphan = idp.seed("maria.oliveira", "maria.oliveira@empresa.com", "Maria", "Antiga")
        r = admin.post("/users", json=_new_user_payload())
        assert r.status_code == 201, r.text
        assert not any(call[0] == "create_user" for call in idp.calls)
        db = _TestSession()
        identity = db.scalar(select(OidcIdentity).where(OidcIdentity.subject == orphan))
        assert identity is not None
        db.close()
        assert idp.accounts[orphan]["lastName"] == "Oliveira"
        assert idp.passwords[orphan]["temporary"] is True

    def test_usuario_ja_usado_por_outra_conta(self, admin, idp):
        idp.seed("maria.oliveira", "outra@empresa.com")
        r = admin.post("/users", json=_new_user_payload())
        assert r.status_code == 409 and r.json()["code"] == "username_taken"

    def test_falha_no_banco_desfaz_conta_no_keycloak(self, admin, idp, monkeypatch):
        def boom(*args, **kwargs):
            raise RuntimeError("falha simulada")
        monkeypatch.setattr("app.services.user_admin.record_audit", boom)
        r = admin.post("/users", json=_new_user_payload())
        assert r.status_code == 500
        assert idp.find_by_username("maria.oliveira") is None
        assert any(call[0] == "delete_user" for call in idp.calls)
        db = _TestSession()
        assert db.scalar(select(AppUser).where(AppUser.email == "maria.oliveira@empresa.com")) is None
        db.close()

    def test_senha_nunca_persistida_nem_devolvida(self, admin, idp):
        r = admin.post("/users", json=_new_user_payload())
        assert TEMP_PASSWORD not in r.text
        user_id = r.json()["user"]["id"]
        r2 = admin.post(f"/users/{user_id}/reset-password", json={"temporary_password": "Outra#Senha-771"})
        assert r2.status_code == 200 and "Outra#Senha-771" not in r2.text
        db = _TestSession()
        dump = json.dumps([
            [log.old_values, log.new_values, log.metadata_] for log in db.scalars(select(AuditLog)).all()
        ])
        users_dump = json.dumps([[u.email, u.username, u.display_name] for u in db.scalars(select(AppUser)).all()])
        db.close()
        for secret in (TEMP_PASSWORD, "Outra#Senha-771"):
            assert secret not in dump and secret not in users_dump

    def test_validacoes_de_entrada(self, admin, idp):
        assert admin.post("/users", json=_new_user_payload(display_name="Maria")).status_code == 422
        assert admin.post("/users", json=_new_user_payload(email="invalido")).status_code == 422
        assert admin.post("/users", json=_new_user_payload(temporary_password="123")).status_code == 422
        assert admin.post("/users", json=_new_user_payload(profile="SUPERUSER")).status_code == 422
        assert idp.find_by_username("maria.oliveira") is None

    def test_usuario_gerado_a_partir_do_email(self, admin, idp):
        r = admin.post("/users", json=_new_user_payload(username=None, email="João.Silva@Empresa.com"))
        assert r.status_code == 201, r.text
        assert r.json()["user"]["username"] == "joao.silva"

    def test_modo_email_sem_smtp_e_recusado(self, admin, idp):
        r = admin.post("/users", json=_new_user_payload(password_mode="email", temporary_password=None))
        assert r.status_code == 409 and r.json()["code"] == "email_not_configured"
        assert idp.find_by_username("maria.oliveira") is None

    def test_modo_email_com_smtp_envia_update_password(self, admin, idp):
        idp.smtp = True
        r = admin.post("/users", json=_new_user_payload(password_mode="email", temporary_password=None))
        assert r.status_code == 201, r.text
        account = idp.find_by_username("maria.oliveira")
        assert idp.accounts[account.id]["requiredActions"] == ["UPDATE_PASSWORD"]
        assert ("send_update_password_email", account.id) in idp.calls
        assert account.id not in idp.passwords

    def test_capabilities(self, admin, idp):
        assert admin.get("/users/capabilities").json() == {
            "identity_admin": True, "email_actions": False, "password_min_length": 8,
        }


# ─── 7. Bloqueio, reativação e proteções ──────────────────────────────────────

class TestStatusAndProtection:
    def test_usuario_bloqueado_perde_acesso(self, admin, analyst, idp):
        assert analyst.get("/auth/me").status_code == 200
        r = admin.post(f"/users/{analyst.user_id}/deactivate")
        assert r.status_code == 200 and r.json()["user"]["status"] == "disabled"
        # Sessão revogada: sem sessão parcialmente ativa.
        assert analyst.get("/auth/me").status_code == 401
        account = idp.find_by_username("ana")
        assert account.enabled is False
        assert ("logout_user", account.id) in idp.calls

    def test_usuario_bloqueado_nao_cria_sessao_no_callback(self, idp, monkeypatch):
        subject = idp.seed("bia", "bia@empresa.com")
        _make_user("bia@empresa.com", "ANALISTA", status="disabled", subject=subject)
        monkeypatch.setattr(auth_routes, "exchange_code", lambda code, verifier: {"access_token": "at", "id_token": "idt"})
        monkeypatch.setattr(auth_routes, "get_userinfo", lambda token: {"sub": subject, "email": "bia@empresa.com"})
        auth_routes._pending_states["st-disabled"] = {"verifier": "v"}
        with TestClient(fastapi_app, raise_server_exceptions=False) as c:
            r = c.get("/auth/callback?code=x&state=st-disabled", follow_redirects=False)
        assert r.status_code == 302
        assert r.headers["location"].endswith("/login?auth_error=disabled")
        assert "om_session=" not in r.headers.get("set-cookie", "")

    def test_callback_bloqueado_encerra_sso_no_keycloak(self, idp, monkeypatch):
        subject = idp.seed("bia", "bia@empresa.com")
        _make_user("bia@empresa.com", "ANALISTA", status="disabled", subject=subject)
        monkeypatch.setattr(auth_routes, "exchange_code", lambda code, verifier: {"access_token": "at", "id_token": "idt"})
        monkeypatch.setattr(auth_routes, "get_userinfo", lambda token: {"sub": subject, "email": "bia@empresa.com"})
        monkeypatch.setattr(auth_routes, "OIDC_ISSUER_URL", "http://kc/realms/dev")
        monkeypatch.setattr(auth_service, "_oidc_config_cache", {"end_session_endpoint": "http://kc/logout"})
        monkeypatch.setattr(auth_service, "OIDC_CLIENT_ID", "chat-bot-om-bff")
        auth_routes._pending_states["st-sso"] = {"verifier": "v"}
        with TestClient(fastapi_app, raise_server_exceptions=False) as c:
            r = c.get("/auth/callback?code=x&state=st-sso", follow_redirects=False)
        location = urlsplit(r.headers["location"])
        params = parse_qs(location.query)
        assert location.path == "/logout"
        assert params["id_token_hint"] == ["idt"]
        assert params["client_id"] == ["chat-bot-om-bff"]
        assert params["post_logout_redirect_uri"][0].endswith("/login?auth_error=disabled")

    def test_reativar_usuario(self, admin, analyst, idp):
        admin.post(f"/users/{analyst.user_id}/deactivate")
        r = admin.post(f"/users/{analyst.user_id}/activate")
        assert r.status_code == 200 and r.json()["user"]["status"] == "active"
        assert idp.find_by_username("ana").enabled is True

    def test_admin_nao_desativa_a_propria_conta(self, admin):
        r = admin.post(f"/users/{admin.user_id}/deactivate")
        assert r.status_code == 409 and r.json()["code"] == "self_disable"

    def test_unico_admin_nao_remove_o_proprio_perfil(self, admin):
        r = admin.patch(f"/users/{admin.user_id}", json={"profile": "ANALISTA"})
        assert r.status_code == 409 and r.json()["code"] == "last_admin"
        db = _TestSession()
        assert admin.user_id in active_admin_ids(db)
        db.close()

    def test_com_outro_admin_pode_remover_o_proprio_perfil(self, admin, idp):
        _make_user("segundo@empresa.com", "ADMINISTRADOR", subject=idp.seed("segundo", "segundo@empresa.com"))
        r = admin.patch(f"/users/{admin.user_id}", json={"profile": "ANALISTA"})
        assert r.status_code == 200 and r.json()["user"]["profile"] == "ANALISTA"

    def test_admin_desativa_outro_admin(self, admin, idp):
        other = _make_user("segundo@empresa.com", "ADMINISTRADOR", subject=idp.seed("segundo", "segundo@empresa.com"))
        assert admin.post(f"/users/{other}/deactivate").status_code == 200

    def test_deny_de_users_manage_no_proprio_admin_bloqueado(self, admin):
        r = admin.post(f"/users/{admin.user_id}/permission-overrides",
                       json={"permission_code": "users.manage", "effect": "deny"})
        assert r.status_code == 409

    def test_editar_nome_e_perfil(self, admin, analyst, idp):
        r = admin.patch(f"/users/{analyst.user_id}", json={"display_name": "Ana Paula Souza", "profile": "GERENTE"})
        assert r.status_code == 200
        assert r.json()["user"]["display_name"] == "Ana Paula Souza"
        assert r.json()["user"]["profile"] == "GERENTE"
        account = idp.find_by_username("ana")
        assert (account.first_name, account.last_name) == ("Ana", "Paula Souza")

    def test_aprovar_usuario_pendente(self, admin, idp):
        pending = _make_user("novo@empresa.com", None, status="pending", subject=idp.seed("novo", "novo@empresa.com"))
        assert admin.patch(f"/users/{pending}", json={"status": "active"}).json()["code"] == "profile_required"
        r = admin.patch(f"/users/{pending}", json={"status": "active", "profile": "CONVIDADO"})
        assert r.status_code == 200 and r.json()["user"]["status"] == "active"

    def test_redefinir_senha_temporaria_encerra_sessoes(self, admin, analyst, idp):
        r = admin.post(f"/users/{analyst.user_id}/reset-password", json={"temporary_password": TEMP_PASSWORD})
        assert r.status_code == 200
        account = idp.find_by_username("ana")
        assert idp.passwords[account.id] == {"value": TEMP_PASSWORD, "temporary": True}
        assert analyst.get("/auth/me").status_code == 401

    def test_reenviar_email_exige_smtp(self, admin, analyst, idp):
        r = admin.post(f"/users/{analyst.user_id}/password-email")
        assert r.status_code == 409 and r.json()["code"] == "email_not_configured"
        idp.smtp = True
        assert admin.post(f"/users/{analyst.user_id}/password-email").status_code == 200


# ─── 8. Pré-provisionamento DEV e primeiro login ──────────────────────────────

class TestDevProvisioning:
    def _seed_dev(self, idp):
        return {
            username: idp.seed(username, f"{username}@local", username.split(".")[0].title(), "OM")
            for username in ("admin.om", "analista.om", "gerente.om", "diretor.om", "convidado.om")
        }

    def test_provisiona_usuarios_dev_ativos_com_perfil(self, idp):
        subjects = self._seed_dev(idp)
        db = _TestSession()
        provision_dev_users(db, idp)
        provision_dev_users(db, idp)  # idempotente
        expected = {"admin.om": "ADMINISTRADOR", "analista.om": "ANALISTA", "gerente.om": "GERENTE",
                    "diretor.om": "DIRETOR", "convidado.om": "CONVIDADO"}
        for username, profile in expected.items():
            user = db.scalar(select(AppUser).where(AppUser.username == username))
            assert user.status == "active"
            assert db.get(Profile, user.profile_id).name == profile
            identities = db.scalars(select(OidcIdentity).where(OidcIdentity.user_id == user.id)).all()
            assert [i.subject for i in identities] == [subjects[username]]
        assert db.scalar(select(func.count(AppUser.id))) == 5
        db.close()

    def test_provisionamento_libera_pendente_e_preserva_bloqueio(self, idp):
        subjects = self._seed_dev(idp)
        _make_user("analista.om@local", None, status="pending", subject=subjects["analista.om"])
        _make_user("gerente.om@local", "GERENTE", status="disabled", subject=subjects["gerente.om"])
        db = _TestSession()
        provision_dev_users(db, idp)
        analista = db.scalar(select(AppUser).where(AppUser.email == "analista.om@local"))
        gerente = db.scalar(select(AppUser).where(AppUser.email == "gerente.om@local"))
        assert analista.status == "active" and db.get(Profile, analista.profile_id).name == "ANALISTA"
        assert gerente.status == "disabled"
        db.close()

    def test_primeiro_login_do_analista_dev(self, idp, monkeypatch):
        subjects = self._seed_dev(idp)
        db = _TestSession()
        provision_dev_users(db, idp)
        db.close()

        monkeypatch.setattr(auth_routes, "exchange_code", lambda code, verifier: {"access_token": "at", "id_token": "idt"})
        monkeypatch.setattr(auth_routes, "get_userinfo", lambda token: {
            "sub": subjects["analista.om"], "email": "analista.om@local",
            "preferred_username": "analista.om", "name": "Analista OM",
        })
        auth_routes._pending_states["st-first"] = {"verifier": "v"}
        with TestClient(fastapi_app, raise_server_exceptions=False) as c:
            r = c.get("/auth/callback?code=x&state=st-first", follow_redirects=False)
            assert r.status_code == 302 and r.headers["location"] == "http://localhost:5173"
            assert "om_session=" in r.headers["set-cookie"]
            me = c.get("/auth/me")
        assert me.status_code == 200
        body = me.json()
        assert body["profile"] == "ANALISTA" and body["status"] == "active"
        assert body["username"] == "analista.om"
        assert "users.manage" not in body["permissions"]

        db = _TestSession()
        user = db.scalar(select(AppUser).where(AppUser.username == "analista.om"))
        assert user.last_seen_at is not None
        session = db.scalar(select(UserSession).where(UserSession.user_id == user.id))
        assert session.id_token_hint == "idt"
        db.close()

    def test_identidade_desconhecida_continua_pendente(self, idp, monkeypatch):
        monkeypatch.setattr(auth_service, "BOOTSTRAP_ADMIN_EMAIL", "")
        db = _TestSession()
        user = resolve_or_create_user(db, {"sub": "estranho", "email": "estranho@empresa.com",
                                           "preferred_username": "estranho"})
        assert user.status == "pending" and user.profile_id is None and user.username == "estranho"
        db.close()


# ─── 9-10. /auth/me e logout ──────────────────────────────────────────────────

class TestSessionEndpoints:
    def test_auth_me_continua_funcionando(self, analyst):
        r = analyst.get("/auth/me")
        assert r.status_code == 200
        body = r.json()
        assert body["email"] == "ana@empresa.com" and body["profile"] == "ANALISTA"
        assert body["csrf_token"] and "permissions" in body

    def test_logout_revoga_sessao(self, analyst):
        r = analyst.post("/auth/logout")
        assert r.status_code == 200
        assert r.json()["logout_url"].endswith("/login")
        assert analyst.get("/auth/me").status_code == 401

    def test_logout_oidc_usa_id_token_hint(self, idp, monkeypatch):
        user_id = _make_user("carlos@empresa.com", "ANALISTA")
        db = _TestSession()
        token = create_session(db, user_id, id_token="id-token-abc")
        csrf = db.scalar(select(UserSession).where(UserSession.user_id == user_id)).csrf_secret
        db.close()
        monkeypatch.setattr(auth_routes, "OIDC_ISSUER_URL", "http://kc/realms/dev")
        monkeypatch.setattr(auth_service, "_oidc_config_cache", {"end_session_endpoint": "http://kc/logout"})
        monkeypatch.setattr(auth_service, "OIDC_CLIENT_ID", "chat-bot-om-bff")
        with TestClient(fastapi_app, raise_server_exceptions=False) as c:
            c.cookies.set(SESSION_COOKIE, token)
            r = c.post("/auth/logout", headers={"X-CSRF-Token": csrf})
            assert r.status_code == 200
            params = parse_qs(urlsplit(r.json()["logout_url"]).query)
            assert params["id_token_hint"] == ["id-token-abc"]
            assert params["client_id"] == ["chat-bot-om-bff"]
            assert params["post_logout_redirect_uri"][0].endswith("/login")
            assert c.get("/auth/me").status_code == 401
        db = _TestSession()
        assert db.scalar(select(UserSession).where(UserSession.user_id == user_id)).id_token_hint is None
        db.close()

    def test_logout_de_usuario_bloqueado_ainda_funciona(self):
        user_id = _make_user("bloqueado@empresa.com", "ANALISTA", status="disabled")
        client = _client_for(user_id)
        try:
            assert client.post("/auth/logout").status_code == 200
        finally:
            client.__exit__(None, None, None)


# ─── Utilitários ──────────────────────────────────────────────────────────────

def test_username_from_email():
    assert username_from_email("João.Silva@empresa.com") == "joao.silva"
    assert username_from_email("maria+teste@empresa.com") == "maria.teste"


def test_validate_display_name():
    assert validate_display_name("  Ana   Paula  ") == "Ana Paula"
    with pytest.raises(UserAdminError):
        validate_display_name("Ana")
    with pytest.raises(UserAdminError):
        validate_display_name("Ana <script>")
