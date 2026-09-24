import re

from sqlglot import exp, parse
from sqlglot.errors import ParseError
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.qa_trace import register_qa_trace


MAX_ROWS = 200

TABELAS_PERMITIDAS = {
    "services",
    "uploads",
}

COMANDOS_PROIBIDOS = {
    "insert",
    "update",
    "delete",
    "drop",
    "alter",
    "truncate",
    "create",
    "grant",
    "revoke",
    "copy",
    "vacuum",
    "analyze",
    "comment",
}


class ChatbotQueryError(Exception):
    pass


def validar_sql(sql: str) -> str:
    sql_limpo = sql.strip()

    # Permite um ; apenas no final
    if sql_limpo.endswith(";"):
        sql_limpo = sql_limpo[:-1].strip()

    if not sql_limpo:
        raise ChatbotQueryError("A consulta SQL está vazia.")

    # Nesta aplicação o chatbot só pode realizar consultas
    if not re.match(r"^(select|with)\b", sql_limpo, re.IGNORECASE):
        raise ChatbotQueryError(
            "Somente consultas SELECT ou WITH ... SELECT são permitidas."
        )

    sql_lower = sql_limpo.lower()

    # Impede múltiplas instruções
    if ";" in sql_limpo:
        raise ChatbotQueryError(
            "Não é permitido executar múltiplas instruções SQL."
        )

    # Bloqueia comandos de escrita/administração
    for comando in COMANDOS_PROIBIDOS:
        if re.search(rf"\b{comando}\b", sql_lower):
            raise ChatbotQueryError(
                f"Comando não permitido: {comando.upper()}."
            )

    try:
        statements = parse(sql_limpo, read="postgres")
    except ParseError as exc:
        raise ChatbotQueryError("A consulta SQL é inválida.") from exc

    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        raise ChatbotQueryError(
            "Somente consultas SELECT ou WITH ... SELECT são permitidas."
        )

    statement = statements[0]
    aliases_cte = {
        cte.alias_or_name.lower()
        for cte in statement.find_all(exp.CTE)
    }

    # O AST distingue tabelas reais do FROM interno de funções como EXTRACT.
    for tabela in statement.find_all(exp.Table):
        nome_tabela = tabela.name.lower()

        if nome_tabela in aliases_cte:
            continue

        if nome_tabela not in TABELAS_PERMITIDAS:
            raise ChatbotQueryError(
                f"Tabela não autorizada para o chatbot: {nome_tabela}."
            )

    return sql_limpo


def executar_consulta_chatbot(
    db: Session,
    sql: str,
    qa_trace_id: str | None = None,
) -> dict:
    sql_validado = validar_sql(sql)
    filas = []
    truncated = False

    try:
        resultado = db.execute(text(sql_validado))
        colunas = list(resultado.keys())

        registros = resultado.mappings().fetchmany(MAX_ROWS + 1)
        truncated = len(registros) > MAX_ROWS
        if truncated:
            registros = registros[:MAX_ROWS]
        filas = [dict(registro) for registro in registros]
        row_count = len(filas)
        success = True
        error = None
    except Exception as exc:
        colunas = []
        row_count = 0
        success = False
        error = str(exc)
        raise ChatbotQueryError(str(exc)) from exc
    finally:
        if qa_trace_id:
            register_qa_trace(
                trace_id=qa_trace_id,
                sql=sql,
                sql_validado=sql_validado,
                success=success,
                row_count=row_count,
                truncated=truncated,
                error=error,
            )

    return {
        "success": success,
        "row_count": row_count,
        "truncated": truncated,
        "columns": colunas,
        "rows": filas,
    }