"""
Cliente mínimo da Keycloak Admin REST API — uso exclusivo do backend.

O navegador nunca fala com a Admin API. O backend autentica com um client
confidencial dedicado (service account, grant ``client_credentials``) que tem
apenas os papéis de ``realm-management`` necessários para gerir usuários.

Regras de segurança:
- o token de serviço fica apenas em memória do processo;
- senhas recebidas são repassadas somente ao Keycloak e nunca entram em
  mensagens de erro, exceções ou logs.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

import httpx

from app.core.config import (
    KEYCLOAK_ACTION_EMAIL_LIFESPAN_SECONDS,
    KEYCLOAK_ADMIN_BASE_URL,
    KEYCLOAK_ADMIN_CLIENT_ID,
    KEYCLOAK_ADMIN_CLIENT_SECRET,
    KEYCLOAK_ADMIN_TIMEOUT_SECONDS,
    KEYCLOAK_REALM,
    OIDC_CLIENT_ID,
    OIDC_ISSUER_URL,
)

logger = logging.getLogger(__name__)

_SMTP_CACHE_SECONDS = 60


class IdentityAdminError(Exception):
    """Falha ao executar uma operação administrativa no provedor de identidade.

    ``message`` é sempre uma mensagem segura para exibir ao administrador.
    """

    def __init__(self, message: str, *, status_code: int = 502, code: str = "identity_provider_error") -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


@dataclass
class IdentityUser:
    id: str
    username: str
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    enabled: bool = True
    email_verified: bool = False
    required_actions: list[str] = field(default_factory=list)

    @classmethod
    def from_representation(cls, rep: dict[str, Any]) -> "IdentityUser":
        return cls(
            id=rep.get("id", ""),
            username=rep.get("username", ""),
            email=(rep.get("email") or None),
            first_name=rep.get("firstName"),
            last_name=rep.get("lastName"),
            enabled=bool(rep.get("enabled", True)),
            email_verified=bool(rep.get("emailVerified", False)),
            required_actions=list(rep.get("requiredActions") or []),
        )

    @property
    def full_name(self) -> str:
        return " ".join(part for part in (self.first_name, self.last_name) if part).strip()


def _split_issuer(issuer: str) -> tuple[str, str]:
    """``http://host/realms/nome`` → (``http://host``, ``nome``)."""
    issuer = (issuer or "").rstrip("/")
    marker = "/realms/"
    if marker not in issuer:
        return "", ""
    base, realm = issuer.split(marker, 1)
    return base, realm.split("/", 1)[0]


# Mensagens do Keycloak traduzidas para textos amigáveis ao administrador.
_FRIENDLY_ERRORS = {
    "User exists with same username": "Este nome de usuário já está em uso no provedor de identidade.",
    "User exists with same email": "Este e-mail já está em uso no provedor de identidade.",
    "User exists with same username or email": "Já existe uma conta com este usuário ou e-mail no provedor de identidade.",
    "error-person-name-invalid-character": "O nome contém caracteres não permitidos.",
    "error-invalid-email": "Informe um e-mail válido.",
    "invalidEmailMessage": "Informe um e-mail válido.",
    "error-invalid-length": "Algum campo excede o tamanho permitido.",
    "error-username-invalid-character": "O nome de usuário contém caracteres não permitidos.",
    "invalidPasswordMinLengthMessage": "A senha não atende ao tamanho mínimo exigido.",
    "invalidPasswordMinDigitsMessage": "A senha precisa conter mais números.",
    "invalidPasswordMinUpperCaseCharsMessage": "A senha precisa conter letras maiúsculas.",
    "invalidPasswordMinLowerCaseCharsMessage": "A senha precisa conter letras minúsculas.",
    "invalidPasswordMinSpecialCharsMessage": "A senha precisa conter caracteres especiais.",
    "invalidPasswordNotUsernameMessage": "A senha não pode ser igual ao nome de usuário.",
    "invalidPasswordNotEmailMessage": "A senha não pode ser igual ao e-mail.",
    "invalidPasswordHistoryMessage": "A senha não pode repetir uma senha recente.",
    "invalidPasswordBlacklistedMessage": "Esta senha é muito comum. Escolha outra.",
}


def _extract_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return ""
    if isinstance(payload, dict):
        for key in ("errorMessage", "error_description", "error"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
        errors = payload.get("errors")
        if isinstance(errors, list) and errors and isinstance(errors[0], dict):
            return str(errors[0].get("errorMessage") or "")
    return ""


def _friendly(raw: str, fallback: str) -> str:
    if not raw:
        return fallback
    for key, text in _FRIENDLY_ERRORS.items():
        if key in raw:
            return text
    if raw.startswith("Password policy not met") or raw.startswith("invalidPassword"):
        return "A senha não atende à política de senhas do provedor de identidade."
    return fallback


class KeycloakAdminClient:
    def __init__(
        self,
        *,
        base_url: str,
        realm: str,
        client_id: str,
        client_secret: str,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.realm = realm
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout = timeout
        self._transport = transport
        self._token: str | None = None
        self._token_expires_at = 0.0
        self._lock = threading.Lock()
        self._smtp_cache: tuple[float, bool] | None = None

    # ── Configuração ─────────────────────────────────────────────────────────
    def is_configured(self) -> bool:
        return bool(self.base_url and self.realm and self.client_id and self.client_secret)

    def _require_configured(self) -> None:
        if not self.is_configured():
            raise IdentityAdminError(
                "A integração administrativa com o provedor de identidade não está configurada.",
                status_code=503,
                code="identity_admin_not_configured",
            )

    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=self.timeout, transport=self._transport)

    # ── Token de serviço ─────────────────────────────────────────────────────
    def _service_token(self, *, force: bool = False) -> str:
        with self._lock:
            now = time.monotonic()
            if not force and self._token and now < self._token_expires_at:
                return self._token
            url = f"{self.base_url}/realms/{quote(self.realm)}/protocol/openid-connect/token"
            try:
                with self._client() as client:
                    resp = client.post(url, data={
                        "grant_type": "client_credentials",
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                    })
            except httpx.HTTPError as exc:
                logger.warning("Keycloak Admin: falha de conexão ao obter token: %s", type(exc).__name__)
                raise IdentityAdminError("Não foi possível contatar o provedor de identidade.") from None
            if resp.status_code != 200:
                logger.warning("Keycloak Admin: token de serviço recusado (HTTP %s).", resp.status_code)
                raise IdentityAdminError(
                    "O provedor de identidade recusou as credenciais administrativas do Chat-bot O&M.",
                    code="identity_admin_unauthorized",
                )
            payload = resp.json()
            self._token = payload["access_token"]
            self._token_expires_at = now + max(10, int(payload.get("expires_in", 60)) - 30)
            return self._token

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
        expected: tuple[int, ...] = (200,),
        fallback_message: str = "O provedor de identidade não concluiu a operação.",
    ) -> httpx.Response:
        self._require_configured()
        url = f"{self.base_url}/admin/realms/{quote(self.realm)}{path}"
        for attempt in (1, 2):
            token = self._service_token(force=attempt == 2)
            try:
                with self._client() as client:
                    resp = client.request(
                        method, url, json=json, params=params,
                        headers={"Authorization": f"Bearer {token}"},
                    )
            except httpx.HTTPError as exc:
                logger.warning("Keycloak Admin: falha de conexão em %s %s: %s", method, path, type(exc).__name__)
                raise IdentityAdminError("Não foi possível contatar o provedor de identidade.") from None
            if resp.status_code == 401 and attempt == 1:
                continue  # token expirado/revogado: renova uma vez
            break

        if resp.status_code in expected:
            return resp

        raw = _extract_error(resp)
        logger.warning("Keycloak Admin: %s %s → HTTP %s (%s)", method, path, resp.status_code, raw or "sem detalhe")
        if resp.status_code == 403:
            raise IdentityAdminError(
                "O Chat-bot O&M não tem permissão para esta operação no provedor de identidade.",
                code="identity_admin_forbidden",
            )
        if resp.status_code == 404:
            raise IdentityAdminError("Conta não encontrada no provedor de identidade.", status_code=404, code="identity_user_not_found")
        if resp.status_code == 409:
            raise IdentityAdminError(_friendly(raw, "Já existe uma conta com estes dados no provedor de identidade."), status_code=409, code="identity_conflict")
        if resp.status_code == 400:
            raise IdentityAdminError(_friendly(raw, "O provedor de identidade recusou os dados informados."), status_code=422, code="identity_validation")
        raise IdentityAdminError(_friendly(raw, fallback_message))

    # ── Consultas ────────────────────────────────────────────────────────────
    def _search(self, **params: str) -> list[IdentityUser]:
        resp = self._request("GET", "/users", params={**params, "exact": "true", "briefRepresentation": "false"})
        return [IdentityUser.from_representation(rep) for rep in resp.json() or []]

    def find_by_username(self, username: str) -> IdentityUser | None:
        username = (username or "").strip().lower()
        if not username:
            return None
        return next((u for u in self._search(username=username) if u.username.lower() == username), None)

    def find_by_email(self, email: str) -> IdentityUser | None:
        email = (email or "").strip().lower()
        if not email:
            return None
        return next((u for u in self._search(email=email) if (u.email or "").lower() == email), None)

    def get_user(self, user_id: str) -> IdentityUser | None:
        try:
            resp = self._request("GET", f"/users/{quote(user_id)}")
        except IdentityAdminError as exc:
            if exc.status_code == 404:
                return None
            raise
        return IdentityUser.from_representation(resp.json())

    def smtp_configured(self) -> bool:
        """Indica se o realm tem SMTP configurado (necessário para e-mails de ação)."""
        now = time.monotonic()
        if self._smtp_cache and now - self._smtp_cache[0] < _SMTP_CACHE_SECONDS:
            return self._smtp_cache[1]
        resp = self._request("GET", "")
        smtp = (resp.json() or {}).get("smtpServer") or {}
        configured = bool(smtp.get("host"))
        self._smtp_cache = (now, configured)
        return configured

    # ── Escrita ──────────────────────────────────────────────────────────────
    def create_user(
        self,
        *,
        username: str,
        email: str,
        first_name: str,
        last_name: str,
        enabled: bool = True,
        temporary_password: str | None = None,
        required_actions: list[str] | None = None,
    ) -> str:
        """Cria a conta e retorna o ``id`` (subject OIDC) gerado pelo Keycloak."""
        payload: dict[str, Any] = {
            "username": username,
            "email": email,
            "firstName": first_name,
            "lastName": last_name,
            "enabled": enabled,
            # E-mail informado pelo administrador da organização.
            "emailVerified": True,
            "requiredActions": list(required_actions or []),
        }
        if temporary_password:
            payload["credentials"] = [{"type": "password", "value": temporary_password, "temporary": True}]
        resp = self._request("POST", "/users", json=payload, expected=(201,),
                             fallback_message="Não foi possível criar a conta no provedor de identidade.")
        location = resp.headers.get("Location", "")
        user_id = location.rstrip("/").rsplit("/", 1)[-1] if location else ""
        if not user_id:
            created = self.find_by_username(username)
            if created is None:
                raise IdentityAdminError("A conta foi criada, mas o provedor não informou o identificador.")
            user_id = created.id
        return user_id

    def update_user(
        self,
        user_id: str,
        *,
        first_name: str | None = None,
        last_name: str | None = None,
        enabled: bool | None = None,
    ) -> None:
        """Atualiza campos preservando o restante da representação (GET → PUT)."""
        rep = self._request("GET", f"/users/{quote(user_id)}").json()
        if first_name is not None:
            rep["firstName"] = first_name
        if last_name is not None:
            rep["lastName"] = last_name
        if enabled is not None:
            rep["enabled"] = enabled
        # Campos somente leitura/derivados que o PUT não aceita de volta.
        for key in ("access", "createdTimestamp", "totp", "disableableCredentialTypes", "notBefore", "userProfileMetadata"):
            rep.pop(key, None)
        self._request("PUT", f"/users/{quote(user_id)}", json=rep, expected=(204,),
                      fallback_message="Não foi possível atualizar a conta no provedor de identidade.")

    def set_temporary_password(self, user_id: str, password: str) -> None:
        self._request(
            "PUT", f"/users/{quote(user_id)}/reset-password",
            json={"type": "password", "value": password, "temporary": True},
            expected=(204,),
            fallback_message="Não foi possível definir a senha temporária.",
        )

    def send_update_password_email(self, user_id: str, *, redirect_client_id: str | None = None) -> None:
        params: dict[str, Any] = {"lifespan": KEYCLOAK_ACTION_EMAIL_LIFESPAN_SECONDS}
        client_id = redirect_client_id if redirect_client_id is not None else OIDC_CLIENT_ID
        if client_id:
            params["client_id"] = client_id
        self._request(
            "PUT", f"/users/{quote(user_id)}/execute-actions-email",
            json=["UPDATE_PASSWORD"], params=params, expected=(204,),
            fallback_message="Não foi possível enviar o e-mail de definição de senha.",
        )

    def logout_user(self, user_id: str) -> None:
        self._request("POST", f"/users/{quote(user_id)}/logout", expected=(204,))

    def delete_user(self, user_id: str) -> None:
        self._request("DELETE", f"/users/{quote(user_id)}", expected=(204, 404))


def build_default_client() -> KeycloakAdminClient:
    derived_base, derived_realm = _split_issuer(OIDC_ISSUER_URL)
    return KeycloakAdminClient(
        base_url=KEYCLOAK_ADMIN_BASE_URL or derived_base,
        realm=KEYCLOAK_REALM or derived_realm,
        client_id=KEYCLOAK_ADMIN_CLIENT_ID,
        client_secret=KEYCLOAK_ADMIN_CLIENT_SECRET,
        timeout=KEYCLOAK_ADMIN_TIMEOUT_SECONDS,
    )


_default_client: KeycloakAdminClient | None = None


def get_identity_admin() -> KeycloakAdminClient:
    """Dependency do FastAPI — singleton do processo (sobrescrito nos testes)."""
    global _default_client
    if _default_client is None:
        _default_client = build_default_client()
    return _default_client
