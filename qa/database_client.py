from __future__ import annotations

import re

import sqlglot

from typing import Any

from sqlalchemy import create_engine, text

from qa.config import DATABASE_URL


class OracleQueryError(RuntimeError):
    pass


_engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
) if DATABASE_URL else None


def execute_oracle_query(sql: str) -> dict[str, Any]:
    if not DATABASE_URL:
        raise OracleQueryError("DATABASE_URL não configurada para o QA.")

    normalized = (sql or "").strip()

    if not normalized:
        raise OracleQueryError("SQL do oráculo vazio.")

    if not re.match(r"^(select|with)\b", normalized, re.IGNORECASE):
        raise OracleQueryError(
            "A consulta oráculo deve ser somente leitura."
        )

    try:
        statements = sqlglot.parse(
            normalized,
            read="postgres",
        )
    except Exception as exc:
        raise OracleQueryError(
            f"SQL inválido no oráculo: {exc}"
        ) from exc

    statements = [
        statement
        for statement in statements
        if statement is not None
    ]

    if len(statements) != 1:
        raise OracleQueryError(
            "Oráculo não pode conter múltiplas instruções."
        )

    with _engine.connect() as connection:
        result = connection.execute(text(normalized))
        rows = [dict(row) for row in result.mappings().fetchall()]
        columns = list(result.keys())

    return {
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
    }