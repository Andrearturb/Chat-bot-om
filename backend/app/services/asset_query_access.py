"""Comprovante curto de acesso a ativos para o caminho backend → n8n → backend."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from app.core.config import INTERNAL_API_KEY


def issue_asset_query_token(session_id: str, user_id: int) -> str:
    if not INTERNAL_API_KEY:
        raise RuntimeError("INTERNAL_API_KEY não configurada.")
    payload = {"session_id": session_id, "user_id": user_id, "exp": int(time.time()) + 180}
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).rstrip(b"=")
    signature = hmac.new(INTERNAL_API_KEY.encode(), body, hashlib.sha256).hexdigest()
    return f"{body.decode()}.{signature}"


def verify_asset_query_token(token: str, session_id: str) -> bool:
    if not INTERNAL_API_KEY or not token or "." not in token:
        return False
    body_text, signature = token.rsplit(".", 1)
    body = body_text.encode()
    expected = hmac.new(INTERNAL_API_KEY.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return False
    try:
        payload = json.loads(base64.urlsafe_b64decode(body + b"=" * (-len(body) % 4)))
        return (
            payload.get("session_id") == session_id
            and isinstance(payload.get("user_id"), int)
            and isinstance(payload.get("exp"), int)
            and time.time() <= payload["exp"]
        )
    except (ValueError, TypeError, KeyError):
        return False
