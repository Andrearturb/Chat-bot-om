"""Comprovante curto de acesso a consultas para o caminho backend → n8n → backend."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from app.core.config import INTERNAL_API_KEY


VALIDADE_SEGUNDOS = 180


def issue_query_token(session_id: str, user_id: int, domains: list[str]) -> str:
    """Assina quais domínios esta sessão pode consultar, por 3 minutos."""
    if not INTERNAL_API_KEY:
        raise RuntimeError("INTERNAL_API_KEY não configurada.")
    payload = {
        "session_id": session_id,
        "user_id": user_id,
        "domains": sorted(domains),
        "exp": int(time.time()) + VALIDADE_SEGUNDOS,
    }
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).rstrip(b"=")
    signature = hmac.new(INTERNAL_API_KEY.encode(), body, hashlib.sha256).hexdigest()
    return f"{body.decode()}.{signature}"


def verify_query_token(token: str, session_id: str, domain: str) -> bool:
    """Confere assinatura, sessão, validade e se o domínio pedido foi autorizado."""
    if not INTERNAL_API_KEY or not token or "." not in token:
        return False
    body_text, signature = token.rsplit(".", 1)
    body = body_text.encode()
    expected = hmac.new(INTERNAL_API_KEY.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return False
    try:
        payload = json.loads(base64.urlsafe_b64decode(body + b"=" * (-len(body) % 4)))
        domains = payload.get("domains")
        return (
            payload.get("session_id") == session_id
            and isinstance(payload.get("user_id"), int)
            and isinstance(payload.get("exp"), int)
            and time.time() <= payload["exp"]
            # Ausência de "domains" é token do formato antigo: não autoriza nada.
            and isinstance(domains, list)
            and domain in domains
        )
    except (ValueError, TypeError, KeyError):
        return False
