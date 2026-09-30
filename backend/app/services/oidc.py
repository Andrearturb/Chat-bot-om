"""
Cliente OIDC do BFF (Keycloak).

Discovery, JWKS, validação de tokens, troca de código (PKCE), renovação,
revogação (RFC 7009) e validação de logout token. Nenhum token sai deste
backend para o navegador. A configuração é lida de ``app.core.config`` a cada
chamada (os testes a substituem).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
from authlib.jose import JsonWebKey, JsonWebToken
from authlib.jose.errors import JoseError

from app.core import config

logger = logging.getLogger(__name__)

BACKCHANNEL_LOGOUT_EVENT = "http://schemas.openid.net/event/backchannel-logout"
JWKS_MIN_REFRESH_SECONDS = 60
LOGOUT_TOKEN_MAX_AGE_SECONDS = 120
HTTP_TIMEOUT_SECONDS = 10

# Substituíveis nos testes: transporte HTTP (httpx.MockTransport) e relógio do JWKS.
transport: httpx.BaseTransport | None = None
clock = time.monotonic

_jwt = JsonWebToken(["RS256"])
_lock = threading.Lock()
_discovery: dict | None = None
_keys: dict[str, object] = {}
_keys_attempted_at: float | None = None
_keys_last_failed = False


class OidcError(Exception):
    """Token ou resposta inválida. ``code`` é curto e seguro para log."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class OidcRejected(OidcError):
    """O provedor recusou a operação (ex.: invalid_grant, conta bloqueada)."""


class OidcUnavailable(OidcError):
    """Provedor inacessível ou não configurado."""


@dataclass(frozen=True)
class TokenSet:
    access_token: str
    refresh_token: str | None
    id_token: str | None
    access_claims: dict
    id_claims: dict | None


def reset_cache() -> None:
    global _discovery, _keys, _keys_attempted_at, _keys_last_failed
    with _lock:
        _discovery = None
        _keys = {}
        _keys_attempted_at = None
        _keys_last_failed = False


def is_configured() -> bool:
    return bool(config.OIDC_ISSUER_URL)


def issuer() -> str:
    return config.OIDC_ISSUER_URL.rstrip("/")


def _http() -> httpx.Client:
    return httpx.Client(timeout=HTTP_TIMEOUT_SECONDS, transport=transport)


def _get_json(url: str, code: str) -> dict:
    try:
        with _http() as client:
            resp = client.get(url)
    except httpx.HTTPError as exc:
        raise OidcUnavailable(code) from exc
    if resp.status_code != 200:
        raise OidcUnavailable(code)
    try:
        data = resp.json()
    except ValueError as exc:
        raise OidcUnavailable(code) from exc
    if not isinstance(data, dict):
        raise OidcUnavailable(code)
    return data


# ─── Discovery e JWKS ─────────────────────────────────────────────────────────

def discovery() -> dict:
    global _discovery
    if not is_configured():
        raise OidcUnavailable("not_configured")
    if _discovery is None:
        data = _get_json(issuer() + "/.well-known/openid-configuration", "discovery_failed")
        if str(data.get("issuer", "")).rstrip("/") != issuer():
            raise OidcError("issuer_mismatch")
        _discovery = data
    return _discovery


def _refresh_keys() -> dict[str, object]:
    """Busca o JWKS, no máximo uma tentativa por minuto (com ou sem sucesso).

    Só o lock serializa a busca. Quem espera o lock reaproveita o resultado da tentativa
    que acabou de terminar: se ela falhou, levanta OidcUnavailable (o provedor está
    instável, não o token inválido); se deu certo, devolve as chaves atuais.
    """
    global _keys, _keys_attempted_at, _keys_last_failed
    with _lock:
        attempted = _keys_attempted_at
        if attempted is not None and clock() - attempted < JWKS_MIN_REFRESH_SECONDS:
            if _keys_last_failed:
                raise OidcUnavailable("jwks_failed")
            return _keys
        _keys_attempted_at = clock()  # registra a tentativa antes de buscar
        _keys_last_failed = True
        data = _get_json(discovery()["jwks_uri"], "jwks_failed")
        keys = {}
        for jwk in data.get("keys", []):
            if (isinstance(jwk, dict) and jwk.get("kty") == "RSA" and jwk.get("use", "sig") == "sig"
                    and jwk.get("alg", "RS256") == "RS256" and jwk.get("kid")):
                keys[jwk["kid"]] = JsonWebKey.import_key(jwk)
        _keys, _keys_last_failed = keys, False  # o dict é substituído, nunca alterado
        return _keys


def _signing_key(kid: str | None):
    if not kid:
        raise OidcError("missing_kid")
    key = _keys.get(kid)  # caminho sem lock: só para chave já carregada
    if key is None:
        key = _refresh_keys().get(kid)
    if key is None:
        raise OidcError("unknown_signing_key")
    return key


# ─── Validação ────────────────────────────────────────────────────────────────

def _decode(token: str) -> dict:
    if not isinstance(token, str) or not token:
        raise OidcError("invalid_token")
    try:
        claims = _jwt.decode(token, lambda header, payload: _signing_key(header.get("kid")))
    except OidcError:
        raise
    except (JoseError, ValueError, TypeError, KeyError) as exc:
        raise OidcError("invalid_token") from exc
    return dict(claims)


def _check_claims(claims: dict, *, typ: str, require_exp: bool = True) -> None:
    now = time.time()
    skew = config.OIDC_CLOCK_SKEW_SECONDS
    if claims.get("iss") != issuer():
        raise OidcError("invalid_issuer")
    aud = claims.get("aud")
    if config.OIDC_CLIENT_ID not in (aud if isinstance(aud, list) else [aud]):
        raise OidcError("invalid_audience")
    if claims.get("typ") != typ:
        raise OidcError("invalid_token_type")
    iat = claims.get("iat")
    if not isinstance(iat, (int, float)) or iat > now + skew:
        raise OidcError("invalid_iat")
    exp = claims.get("exp")
    if exp is None and not require_exp:
        return
    if not isinstance(exp, (int, float)) or exp < now - skew:
        raise OidcError("token_expired")


def verify_access_token(token: str) -> dict:
    claims = _decode(token)
    _check_claims(claims, typ="Bearer")
    if claims.get("azp") != config.OIDC_CLIENT_ID:
        raise OidcError("invalid_azp")
    if not claims.get("sub"):
        raise OidcError("missing_subject")
    return claims


def verify_id_token(token: str, *, nonce: str | None) -> dict:
    """``nonce=None`` somente na renovação; no login o nonce é obrigatório."""
    claims = _decode(token)
    _check_claims(claims, typ="ID")
    if claims.get("azp") != config.OIDC_CLIENT_ID:
        raise OidcError("invalid_azp")
    if nonce is not None and not hmac.compare_digest(str(claims.get("nonce", "")).encode(), nonce.encode()):
        raise OidcError("invalid_nonce")
    return claims


def verify_logout_token(token: str) -> dict:
    claims = _decode(token)
    _check_claims(claims, typ="Logout", require_exp=False)
    if claims["iat"] < time.time() - LOGOUT_TOKEN_MAX_AGE_SECONDS - config.OIDC_CLOCK_SKEW_SECONDS:
        raise OidcError("logout_token_too_old")
    events = claims.get("events")
    if not isinstance(events, dict) or BACKCHANNEL_LOGOUT_EVENT not in events:
        raise OidcError("invalid_logout_event")
    if "nonce" in claims:
        raise OidcError("nonce_not_allowed")
    if not claims.get("sid") and not claims.get("sub"):
        raise OidcError("missing_sid_and_sub")
    return claims


def roles_from_access_claims(claims: dict) -> list[str]:
    client = (claims.get("resource_access") or {}).get(config.OIDC_CLIENT_ID) or {}
    return [role for role in client.get("roles") or [] if isinstance(role, str)]


# ─── Fluxo de autorização ─────────────────────────────────────────────────────

def code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def authorization_url(*, state: str, nonce: str, code_verifier: str, register: bool = False) -> str:
    params = {
        "response_type": "code",
        "client_id": config.OIDC_CLIENT_ID,
        "redirect_uri": config.OIDC_REDIRECT_URI,
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge(code_verifier),
        "code_challenge_method": "S256",
    }
    if register:
        params["prompt"] = "create"  # abre direto o cadastro do Keycloak
    return discovery()["authorization_endpoint"] + "?" + urlencode(params)


def _token_request(data: dict) -> dict:
    endpoint = discovery()["token_endpoint"]
    payload = {**data, "client_id": config.OIDC_CLIENT_ID, "client_secret": config.OIDC_CLIENT_SECRET}
    try:
        with _http() as client:
            resp = client.post(endpoint, data=payload)
    except httpx.HTTPError as exc:
        raise OidcUnavailable("token_endpoint_unreachable") from exc
    if resp.status_code >= 500:
        raise OidcUnavailable("token_endpoint_error")
    if resp.status_code != 200:
        try:
            error = str(resp.json().get("error") or "rejected")
        except ValueError:
            error = "rejected"
        raise OidcRejected(error[:60])
    return resp.json()


def _token_set(data: dict, *, nonce: str | None, expected_sub: str | None = None) -> TokenSet:
    access_token = data.get("access_token")
    if not access_token:
        raise OidcError("missing_access_token")
    access_claims = verify_access_token(access_token)
    id_token = data.get("id_token")
    id_claims = None
    if id_token:
        id_claims = verify_id_token(id_token, nonce=nonce)
        if id_claims.get("sub") != access_claims["sub"]:
            raise OidcError("subject_mismatch")
    elif nonce is not None:
        raise OidcError("missing_id_token")
    if expected_sub is not None and access_claims["sub"] != expected_sub:
        raise OidcError("subject_mismatch")
    return TokenSet(access_token, data.get("refresh_token"), id_token, access_claims, id_claims)


def exchange_code(code: str, *, code_verifier: str, nonce: str) -> TokenSet:
    data = _token_request({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": config.OIDC_REDIRECT_URI,
        "code_verifier": code_verifier,
    })
    return _token_set(data, nonce=nonce)


def refresh(refresh_token: str, *, expected_sub: str) -> TokenSet:
    data = _token_request({"grant_type": "refresh_token", "refresh_token": refresh_token})
    return _token_set(data, nonce=None, expected_sub=expected_sub)


def revoke_refresh_token(refresh_token: str | None) -> None:
    """Revogação RFC 7009. Melhor esforço: nunca impede o logout local."""
    if not refresh_token or not is_configured():
        return
    try:
        endpoint = discovery().get("revocation_endpoint")
        if not endpoint:
            return
        with _http() as client:
            client.post(endpoint, data={
                "token": refresh_token, "token_type_hint": "refresh_token",
                "client_id": config.OIDC_CLIENT_ID, "client_secret": config.OIDC_CLIENT_SECRET,
            })
    except (OidcError, httpx.HTTPError):
        logger.warning("OIDC: revogação do refresh token falhou; a sessão SSO expira no Keycloak.")


def end_session_url(*, id_token_hint: str | None, post_logout_redirect_uri: str) -> str:
    endpoint = discovery().get("end_session_endpoint")
    if not endpoint:
        return post_logout_redirect_uri
    params = {"post_logout_redirect_uri": post_logout_redirect_uri, "client_id": config.OIDC_CLIENT_ID}
    if id_token_hint:
        params["id_token_hint"] = id_token_hint
    return endpoint + "?" + urlencode(params)
