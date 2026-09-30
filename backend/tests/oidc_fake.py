"""
Provedor OIDC simulado (Keycloak) para os testes.

Assina tokens RS256 com chaves RSA reais e responde discovery, JWKS, token e
revogação via httpx.MockTransport. Os contadores permitem conferir quantas
vezes o backend falou com o provedor.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
import uuid
from urllib.parse import parse_qs, urlsplit

import httpx
from authlib.jose import JsonWebKey, jwt
from cryptography.fernet import Fernet

ISSUER = "http://kc.test/realms/gentil-dev"
CLIENT_ID = "chat-bot-om-bff"
CLIENT_SECRET = "segredo-teste"
REDIRECT_URI = "http://localhost:5173/auth/callback"
ENCRYPTION_KEY = Fernet.generate_key().decode()
BACKCHANNEL_EVENT = "http://schemas.openid.net/event/backchannel-logout"

ANALISTA = ["ANALISTA", "assistant.use", "assistant.history", "indicators.view", "assets.view",
            "assets.create", "assets.edit", "documents.view", "documents.upload", "documents.replace",
            "settings.view"]
ADMINISTRADOR = ["ADMINISTRADOR", "assistant.use", "assistant.history", "indicators.view", "assets.view",
                 "assets.create", "assets.edit", "assets.delete", "assets.import", "documents.view",
                 "documents.upload", "documents.replace", "documents.delete", "audit.view", "users.view",
                 "settings.view", "settings.manage", "sync.tape"]


def s256(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


def authorization_params(url: str) -> dict[str, str]:
    return {key: values[0] for key, values in parse_qs(urlsplit(url).query).items()}


def _new_key():
    return JsonWebKey.generate_key("RSA", 2048, is_private=True)


class FakeProvider:
    def __init__(self) -> None:
        self.kid = "kid-1"
        self.key = _new_key()
        self.published: list[tuple[str, object]] = [(self.kid, self.key)]
        self.codes: dict[str, dict] = {}
        self.refresh_tokens: dict[str, dict] = {}
        self.roles_by_sub: dict[str, list[str]] = {}
        self.disabled_subs: set[str] = set()
        self.revoked: list[str] = []
        self.offline = False
        self.attempts = 0          # toda chamada, inclusive com o provedor fora do ar
        self.jwks_requests = 0
        self.token_requests = 0

    # ── Chaves ────────────────────────────────────────────────────────────────
    def rotate_key(self, *, keep_old: bool = False) -> None:
        self.kid = f"kid-{int(self.kid.split('-')[1]) + 1}"
        self.key = _new_key()
        self.published = (self.published if keep_old else []) + [(self.kid, self.key)]

    def jwks(self) -> dict:
        keys = []
        for kid, key in self.published:
            jwk = key.as_dict(is_private=False)
            jwk.update({"kid": kid, "use": "sig", "alg": "RS256"})
            keys.append(jwk)
        # Como o Keycloak, publica também uma chave de criptografia (não serve para assinatura).
        keys.append({**keys[-1], "kid": "kid-enc", "use": "enc", "alg": "RSA-OAEP"})
        return {"keys": keys}

    def discovery(self) -> dict:
        base = ISSUER + "/protocol/openid-connect"
        return {"issuer": ISSUER, "authorization_endpoint": base + "/auth",
                "token_endpoint": base + "/token", "jwks_uri": base + "/certs",
                "end_session_endpoint": base + "/logout", "revocation_endpoint": base + "/revoke"}

    # ── Tokens ────────────────────────────────────────────────────────────────
    def sign(self, claims: dict, *, kid: str | None = None, key=None, alg: str = "RS256") -> str:
        header = {"alg": alg, "typ": "JWT", "kid": kid or self.kid}
        payload = {name: value for name, value in claims.items() if value is not None}
        return jwt.encode(header, payload, key if key is not None else self.key).decode()

    def access_claims(self, sub: str, roles: list[str], *, sid: str | None = None, **extra) -> dict:
        now = int(time.time())
        return {"iss": ISSUER, "sub": sub, "aud": [CLIENT_ID], "azp": CLIENT_ID, "typ": "Bearer",
                "iat": now, "exp": now + 300, "jti": str(uuid.uuid4()), "sid": sid or f"sid-{sub}",
                "resource_access": {CLIENT_ID: {"roles": list(roles)}},
                "email": f"{sub}@exemplo.local", "preferred_username": sub, "name": f"Pessoa {sub}",
                **extra}

    def id_claims(self, sub: str, *, nonce: str | None, sid: str | None = None, **extra) -> dict:
        now = int(time.time())
        return {"iss": ISSUER, "sub": sub, "aud": CLIENT_ID, "azp": CLIENT_ID, "typ": "ID",
                "iat": now, "exp": now + 300, "nonce": nonce, "sid": sid or f"sid-{sub}",
                "email": f"{sub}@exemplo.local", "preferred_username": sub, "name": f"Pessoa {sub}",
                **extra}

    def logout_claims(self, *, sid: str | None = None, sub: str | None = None, **extra) -> dict:
        now = int(time.time())
        return {"iss": ISSUER, "aud": CLIENT_ID, "typ": "Logout", "iat": now, "exp": now + 120,
                "jti": str(uuid.uuid4()), "events": {BACKCHANNEL_EVENT: {}}, "sid": sid, "sub": sub,
                **extra}

    def issue_code(self, sub: str, roles: list[str], *, nonce: str, code_challenge: str,
                   sid: str | None = None) -> str:
        code = secrets.token_urlsafe(16)
        self.roles_by_sub[sub] = list(roles)
        self.codes[code] = {"sub": sub, "nonce": nonce, "challenge": code_challenge, "sid": sid or f"sid-{sub}"}
        return code

    # ── HTTP ──────────────────────────────────────────────────────────────────
    def handler(self, request: httpx.Request) -> httpx.Response:
        self.attempts += 1
        if self.offline:
            raise httpx.ConnectError("provedor fora do ar", request=request)
        path = request.url.path
        form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()} if request.method == "POST" else {}
        if path.endswith("/.well-known/openid-configuration"):
            return httpx.Response(200, json=self.discovery())
        if path.endswith("/certs"):
            self.jwks_requests += 1
            return httpx.Response(200, json=self.jwks())
        if path.endswith("/token"):
            self.token_requests += 1
            return self._token(form)
        if path.endswith("/revoke"):
            self.revoked.append(form.get("token", ""))
            self.refresh_tokens.pop(form.get("token", ""), None)
            return httpx.Response(200)
        return httpx.Response(404)

    def _token(self, form: dict) -> httpx.Response:
        if form.get("client_id") != CLIENT_ID or form.get("client_secret") != CLIENT_SECRET:
            return httpx.Response(401, json={"error": "unauthorized_client"})
        grant = form.get("grant_type")
        if grant == "authorization_code":
            record = self.codes.pop(form.get("code", ""), None)
            if (record is None or form.get("redirect_uri") != REDIRECT_URI
                    or s256(form.get("code_verifier", "")) != record["challenge"]):
                return httpx.Response(400, json={"error": "invalid_grant"})
            return self._issue(record["sub"], record["sid"], nonce=record["nonce"])
        if grant == "refresh_token":
            # Rotação: cada refresh token vale uma única vez.
            record = self.refresh_tokens.pop(form.get("refresh_token", ""), None)
            if record is None or record["sub"] in self.disabled_subs:
                return httpx.Response(400, json={"error": "invalid_grant"})
            return self._issue(record["sub"], record["sid"], nonce=None)
        return httpx.Response(400, json={"error": "unsupported_grant_type"})

    def _issue(self, sub: str, sid: str, *, nonce: str | None) -> httpx.Response:
        refresh_token = secrets.token_urlsafe(24)
        self.refresh_tokens[refresh_token] = {"sub": sub, "sid": sid}
        roles = self.roles_by_sub.get(sub, [])
        return httpx.Response(200, json={
            "access_token": self.sign(self.access_claims(sub, roles, sid=sid)),
            "id_token": self.sign(self.id_claims(sub, nonce=nonce, sid=sid)),
            "refresh_token": refresh_token, "token_type": "Bearer", "expires_in": 300,
        })


def login_tokens(provider: FakeProvider, sub: str, roles: list[str], *, sid: str | None = None):
    """Faz o login completo (código + PKCE + nonce) e devolve o TokenSet validado."""
    from app.services import oidc

    verifier, nonce = secrets.token_urlsafe(48), secrets.token_urlsafe(16)
    code = provider.issue_code(sub, roles, nonce=nonce, code_challenge=s256(verifier), sid=sid)
    return oidc.exchange_code(code, code_verifier=verifier, nonce=nonce)


def install(monkeypatch, provider: FakeProvider) -> None:
    from app.core import config
    from app.services import oidc

    monkeypatch.setattr(config, "OIDC_ISSUER_URL", ISSUER)
    monkeypatch.setattr(config, "OIDC_CLIENT_ID", CLIENT_ID)
    monkeypatch.setattr(config, "OIDC_CLIENT_SECRET", CLIENT_SECRET)
    monkeypatch.setattr(config, "OIDC_REDIRECT_URI", REDIRECT_URI)
    monkeypatch.setattr(config, "SESSION_ENCRYPTION_KEY", ENCRYPTION_KEY)
    monkeypatch.setattr(oidc, "transport", httpx.MockTransport(provider.handler))
    oidc.reset_cache()
