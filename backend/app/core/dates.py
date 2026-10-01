"""
Datas do backend.

O banco guarda horários em UTC sem fuso (colunas ``DateTime``). Toda data que sai pela
API passa por ``iso_utc``, que acrescenta o "Z": sem ele o navegador lê o horário como
hora local e o mostra deslocado.
"""

from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Agora em UTC, sem fuso: o mesmo formato das colunas do banco."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def iso_utc(value: datetime | None) -> str | None:
    """ISO 8601 em UTC com "Z". Aceita data sem fuso (já em UTC) ou com fuso."""
    if value is None:
        return None
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value.isoformat() + "Z"


def parse_api_datetime(value: str | None) -> datetime | None:
    """Lê uma data ISO 8601 recebida pela API e a converte para UTC sem fuso.

    Sem fuso, a data é tomada como UTC. Valor vazio ou inválido devolve None.
    """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed
