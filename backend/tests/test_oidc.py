"""Validação de tokens e chamadas ao provedor (app/services/oidc.py)."""

from __future__ import annotations

import base64
import json
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
import httpx

from app.services import oidc
from tests.oidc_fake import (
    ANALISTA,
    CLIENT_ID,
    ISSUER,
    FakeProvider,
    authorization_params,
    login_tokens,
    s256,
)


def _unsigned(claims: dict) -> str:
    def b64(obj) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()
    return f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64(claims)}."


def _code(exc_info) -> str:
    return exc_info.value.code


class TestAccessToken:
    def test_token_valido_devolve_claims_e_papeis(self, provider):
        claims = oidc.verify_access_token(provider.sign(provider.access_claims("u1", ANALISTA)))
        assert claims["sub"] == "u1"
        assert oidc.roles_from_access_claims(claims) == ANALISTA

    @pytest.mark.parametrize("change, code", [
        (lambda now: {"iss": "http://outro/realms/gentil-dev"}, "invalid_issuer"),
        (lambda now: {"aud": ["account"]}, "invalid_audience"),
        (lambda now: {"azp": "outro-client"}, "invalid_azp"),
        (lambda now: {"typ": "ID"}, "invalid_token_type"),
        (lambda now: {"exp": now - 60}, "token_expired"),
        (lambda now: {"iat": now + 60}, "invalid_iat"),
        (lambda now: {"sub": None}, "missing_subject"),
    ])
    def test_claims_invalidas_sao_recusadas(self, provider, change, code):
        claims = provider.access_claims("u1", ANALISTA)
        claims.update(change(int(time.time())))
        with pytest.raises(oidc.OidcError) as exc:
            oidc.verify_access_token(provider.sign(claims))
        assert _code(exc) == code

    def test_tolerancia_de_relogio_de_30_segundos(self, provider):
        now = int(time.time())
        claims = provider.access_claims("u1", ANALISTA)
        claims.update({"exp": now - 20, "iat": now + 20})
        assert oidc.verify_access_token(provider.sign(claims))["sub"] == "u1"

    def test_assinatura_de_outra_chave_com_o_mesmo_kid_e_recusada(self, provider):
        intruso = FakeProvider()  # outra chave RSA, mesmo kid "kid-1"
        with pytest.raises(oidc.OidcError) as exc:
            oidc.verify_access_token(intruso.sign(provider.access_claims("u1", ANALISTA)))
        assert _code(exc) == "invalid_token"

    def test_hs256_e_alg_none_sao_recusados(self, provider):
        claims = provider.access_claims("u1", ANALISTA)
        hs256 = provider.sign(claims, alg="HS256", key="chave-simetrica-de-teste-com-32-bytes")
        for token in (hs256, _unsigned(claims), "nao-e-um-jwt"):
            with pytest.raises(oidc.OidcError) as exc:
                oidc.verify_access_token(token)
            assert _code(exc) == "invalid_token"


class TestJwks:
    def test_kid_desconhecido_recarrega_no_maximo_uma_vez_por_minuto(self, provider, monkeypatch):
        now = [1000.0]
        monkeypatch.setattr(oidc, "clock", lambda: now[0])
        oidc.verify_access_token(provider.sign(provider.access_claims("u1", ANALISTA)))
        token = provider.sign(provider.access_claims("u1", ANALISTA), kid="kid-inexistente")
        with pytest.raises(oidc.OidcError) as exc:
            oidc.verify_access_token(token)
        assert _code(exc) == "unknown_signing_key"
        assert provider.jwks_requests == 1  # carregado há menos de 1 minuto
        now[0] += 61
        for _ in range(3):
            with pytest.raises(oidc.OidcError):
                oidc.verify_access_token(token)
        assert provider.jwks_requests == 2  # uma única recarga no novo minuto

    def test_rotacao_de_chave_e_aceita_depois_da_recarga(self, provider, monkeypatch):
        now = [1000.0]
        monkeypatch.setattr(oidc, "clock", lambda: now[0])
        oidc.verify_access_token(provider.sign(provider.access_claims("u1", ANALISTA)))
        provider.rotate_key()
        now[0] += 61
        claims = oidc.verify_access_token(provider.sign(provider.access_claims("u1", ANALISTA)))
        assert claims["sub"] == "u1" and provider.jwks_requests == 2

    def test_falha_na_recarga_tambem_respeita_o_limite_de_um_minuto(self, provider, monkeypatch):
        now = [1000.0]
        monkeypatch.setattr(oidc, "clock", lambda: now[0])
        oidc.verify_access_token(provider.sign(provider.access_claims("u1", ANALISTA)))
        provider.offline = True
        token = provider.sign(provider.access_claims("u1", ANALISTA), kid="kid-inexistente")
        now[0] += 61
        before = provider.attempts
        # Provedor fora do ar: todos recebem "indisponível" (a sessão não deve ser derrubada),
        # mas só a primeira chamada vai à rede.
        for _ in range(4):
            with pytest.raises(oidc.OidcUnavailable):
                oidc.verify_access_token(token)
        assert provider.attempts == before + 1
        # Token com kid já carregado continua válido sem esperar nem tocar a rede.
        assert oidc.verify_access_token(provider.sign(provider.access_claims("u1", ANALISTA)))["sub"] == "u1"
        assert provider.attempts == before + 1
        now[0] += 61
        with pytest.raises(oidc.OidcUnavailable):
            oidc.verify_access_token(token)
        assert provider.attempts == before + 2

    def test_carga_inicial_concorrente_busca_o_jwks_uma_vez(self, provider, monkeypatch):
        original = FakeProvider.jwks
        monkeypatch.setattr(provider, "jwks", lambda: (time.sleep(0.3), original(provider))[1])
        token = provider.sign(provider.access_claims("u1", ANALISTA))
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: oidc.verify_access_token(token)["sub"], range(4)))
        assert results == ["u1"] * 4
        assert provider.jwks_requests == 1

    def test_rotacao_concorrente_busca_o_jwks_uma_vez(self, provider, monkeypatch):
        now = [1000.0]
        monkeypatch.setattr(oidc, "clock", lambda: now[0])
        oidc.verify_access_token(provider.sign(provider.access_claims("u1", ANALISTA)))
        original = FakeProvider.jwks
        monkeypatch.setattr(provider, "jwks", lambda: (time.sleep(0.3), original(provider))[1])
        provider.rotate_key()
        now[0] += 61
        token = provider.sign(provider.access_claims("u1", ANALISTA))
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: oidc.verify_access_token(token)["sub"], range(4)))
        assert results == ["u1"] * 4
        assert provider.jwks_requests == 2

    def test_chave_de_criptografia_nao_valida_assinatura(self, provider):
        token = provider.sign(provider.access_claims("u1", ANALISTA), kid="kid-enc")
        with pytest.raises(oidc.OidcError) as exc:
            oidc.verify_access_token(token)
        assert _code(exc) == "unknown_signing_key"


class TestIdToken:
    def test_nonce_confere(self, provider):
        token = provider.sign(provider.id_claims("u1", nonce="n-1"))
        assert oidc.verify_id_token(token, nonce="n-1")["sub"] == "u1"

    def test_nonce_diferente_ou_ausente_e_recusado(self, provider):
        for claims in (provider.id_claims("u1", nonce="outro"), provider.id_claims("u1", nonce=None)):
            with pytest.raises(oidc.OidcError) as exc:
                oidc.verify_id_token(provider.sign(claims), nonce="n-1")
            assert _code(exc) == "invalid_nonce"

    def test_azp_diferente_ou_ausente_e_recusado(self, provider):
        for extra in ({"azp": "outro-client"}, {"azp": None}):
            claims = provider.id_claims("u1", nonce="n-1", **extra)
            with pytest.raises(oidc.OidcError) as exc:
                oidc.verify_id_token(provider.sign(claims), nonce="n-1")
            assert _code(exc) == "invalid_azp"

    def test_access_token_nao_serve_como_id_token(self, provider):
        with pytest.raises(oidc.OidcError) as exc:
            oidc.verify_id_token(provider.sign(provider.access_claims("u1", ANALISTA)), nonce="n")
        assert _code(exc) == "invalid_token_type"


class TestLogoutToken:
    def test_valido_com_sid_e_dentro_da_tolerancia(self, provider):
        claims = provider.logout_claims(sid="s-1")
        claims["iat"] = int(time.time()) - 140  # 2 min + parte dos 30 s de tolerância
        assert oidc.verify_logout_token(provider.sign(claims))["sid"] == "s-1"

    @pytest.mark.parametrize("change, code", [
        (lambda now: {"iat": now - 151}, "logout_token_too_old"),
        (lambda now: {"events": {}}, "invalid_logout_event"),
        (lambda now: {"nonce": "n"}, "nonce_not_allowed"),
        (lambda now: {"sid": None, "sub": None}, "missing_sid_and_sub"),
        (lambda now: {"typ": "Bearer"}, "invalid_token_type"),
        (lambda now: {"aud": "outro-client"}, "invalid_audience"),
    ])
    def test_invalidos_sao_recusados(self, provider, change, code):
        claims = provider.logout_claims(sid="s-1")
        claims.update(change(int(time.time())))
        with pytest.raises(oidc.OidcError) as exc:
            oidc.verify_logout_token(provider.sign(claims))
        assert _code(exc) == code


class TestTokenEndpoint:
    @pytest.mark.parametrize("status,body", [
        (401, {"error": "invalid_client"}),
        (429, {"error": "temporarily_unavailable"}),
        (200, "<html>indisponível</html>"),
    ])
    def test_erro_transitorio_ou_resposta_invalida_nao_recusa_sessao(self, provider, monkeypatch, status, body):
        monkeypatch.setattr(provider, "_token", lambda _: (
            httpx.Response(status, json=body) if isinstance(body, dict)
            else httpx.Response(status, text=body, headers={"content-type": "text/html"})
        ))
        with pytest.raises(oidc.OidcUnavailable):
            oidc.refresh("token-de-teste", expected_sub="u1")

    def test_troca_de_codigo_com_pkce_e_nonce(self, provider):
        tokens = login_tokens(provider, "u1", ANALISTA)
        assert tokens.access_claims["sub"] == "u1"
        assert tokens.refresh_token and tokens.id_token and tokens.id_claims["sid"] == "sid-u1"

    def test_codigo_reutilizado_e_recusado(self, provider):
        verifier = "v" * 64
        code = provider.issue_code("u1", ANALISTA, nonce="n", code_challenge=s256(verifier))
        oidc.exchange_code(code, code_verifier=verifier, nonce="n")
        with pytest.raises(oidc.OidcRejected) as exc:
            oidc.exchange_code(code, code_verifier=verifier, nonce="n")
        assert _code(exc) == "invalid_grant"

    def test_code_verifier_errado_e_recusado(self, provider):
        code = provider.issue_code("u1", ANALISTA, nonce="n", code_challenge=s256("v" * 64))
        with pytest.raises(oidc.OidcRejected):
            oidc.exchange_code(code, code_verifier="x" * 64, nonce="n")

    def test_nonce_diferente_do_login_e_recusado(self, provider):
        verifier = "v" * 64
        code = provider.issue_code("u1", ANALISTA, nonce="do-provedor", code_challenge=s256(verifier))
        with pytest.raises(oidc.OidcError) as exc:
            oidc.exchange_code(code, code_verifier=verifier, nonce="do-login")
        assert _code(exc) == "invalid_nonce"

    def test_renovacao_gira_o_refresh_token(self, provider):
        tokens = login_tokens(provider, "u1", ANALISTA)
        renewed = oidc.refresh(tokens.refresh_token, expected_sub="u1")
        assert renewed.refresh_token != tokens.refresh_token
        with pytest.raises(oidc.OidcRejected):
            oidc.refresh(tokens.refresh_token, expected_sub="u1")

    def test_renovacao_de_outro_subject_e_recusada(self, provider):
        tokens = login_tokens(provider, "u1", ANALISTA)
        with pytest.raises(oidc.OidcError) as exc:
            oidc.refresh(tokens.refresh_token, expected_sub="u2")
        assert _code(exc) == "subject_mismatch"

    def test_provedor_fora_do_ar(self, provider):
        tokens = login_tokens(provider, "u1", ANALISTA)
        provider.offline = True
        with pytest.raises(oidc.OidcUnavailable):
            oidc.refresh(tokens.refresh_token, expected_sub="u1")

    def test_revogacao_e_melhor_esforco(self, provider):
        tokens = login_tokens(provider, "u1", ANALISTA)
        oidc.revoke_refresh_token(tokens.refresh_token)
        assert provider.revoked == [tokens.refresh_token]
        provider.offline = True
        oidc.revoke_refresh_token("qualquer")  # não levanta exceção


class TestUrls:
    def test_login_com_pkce_s256_nonce_e_state(self, provider):
        url = oidc.authorization_url(state="st", nonce="no", code_verifier="v" * 64)
        params = authorization_params(url)
        assert url.startswith(ISSUER + "/protocol/openid-connect/auth?")
        assert params["code_challenge"] == s256("v" * 64)
        assert params["code_challenge_method"] == "S256"
        assert params["state"] == "st" and params["nonce"] == "no"
        assert params["client_id"] == CLIENT_ID and params["scope"] == "openid email profile"
        assert "prompt" not in params

    def test_cadastro_usa_prompt_create(self, provider):
        url = oidc.authorization_url(state="s", nonce="n", code_verifier="v" * 64, register=True)
        assert authorization_params(url)["prompt"] == "create"

    def test_issuer_divergente_no_discovery_e_recusado(self, provider, monkeypatch):
        monkeypatch.setattr(provider, "discovery", lambda: {**FakeProvider.discovery(provider), "issuer": "http://outro"})
        oidc.reset_cache()
        with pytest.raises(oidc.OidcError) as exc:
            oidc.discovery()
        assert _code(exc) == "issuer_mismatch"

    def test_sem_configuracao_o_provedor_fica_indisponivel(self, provider, monkeypatch):
        from app.core import config
        monkeypatch.setattr(config, "OIDC_ISSUER_URL", "")
        oidc.reset_cache()
        with pytest.raises(oidc.OidcUnavailable):
            oidc.discovery()

    def test_url_de_logout_com_hint_e_client_id(self, provider):
        url = oidc.end_session_url(id_token_hint="tok", post_logout_redirect_uri="http://localhost:5173/login")
        assert url.startswith(ISSUER + "/protocol/openid-connect/logout?")
        assert authorization_params(url) == {"post_logout_redirect_uri": "http://localhost:5173/login",
                                             "client_id": CLIENT_ID, "id_token_hint": "tok"}
