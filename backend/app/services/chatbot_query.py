import re

from sqlglot import exp, parse
from sqlglot.errors import ParseError
from sqlalchemy import text
from sqlalchemy.orm import Session


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

    sql_lower = sql_limpo.lower()

    # Nesta aplicação o chatbot só pode realizar consultas
    if not (
        sql_lower.startswith("select ")
        or sql_lower.startswith("with ")
    ):
        raise ChatbotQueryError(
            "Somente consultas SELECT ou WITH ... SELECT são permitidas."
        )

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
) -> dict:
    sql_validado = validar_sql(sql)

    resultado = db.execute(text(sql_validado))

    colunas = list(resultado.keys())

    # Busca uma linha extra para sabermos se truncamos o resultado
    registros = resultado.mappings().fetchmany(MAX_ROWS + 1)

    truncated = len(registros) > MAX_ROWS

    if truncated:
        registros = registros[:MAX_ROWS]

    rows = [dict(registro) for registro in registros]

    return {
        "success": True,
        "row_count": len(rows),
        "truncated": truncated,
        "columns": colunas,
        "rows": rows,
    }