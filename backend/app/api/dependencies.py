"""
Dependências compartilhadas da API.
"""

import secrets

from fastapi import Header, HTTPException, status

from app.core.config import API_KEY


def verificar_api_key(x_api_key: str = Header(..., alias="x-api-key")) -> None:
    """
    Valida o header x-api-key contra a chave configurada no ambiente.

    Usa comparação em tempo constante (secrets.compare_digest) para
    evitar ataques de timing.
    """
    if not secrets.compare_digest(x_api_key, API_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key inválida ou ausente.",
        )
