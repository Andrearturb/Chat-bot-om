import pytest

from app.services.chatbot_query import ChatbotQueryError, validar_sql


CONSULTAS_VALIDAS = [
    """
    SELECT COUNT(*)
    FROM services
    WHERE EXTRACT(YEAR FROM created_on) = 2026
      AND EXTRACT(MONTH FROM created_on) = 9;
    """,
    """
    SELECT COUNT(*)
    FROM services
    WHERE EXTRACT(YEAR FROM completion_date) = 2026;
    """,
    """
    SELECT status, COUNT(*)
    FROM services
    GROUP BY status;
    """,
    """
    WITH recentes AS (
        SELECT * FROM services
    )
    SELECT * FROM recentes;
    """,
]


@pytest.mark.parametrize("sql", CONSULTAS_VALIDAS)
def test_consultas_validas_sao_aceitas(sql):
    assert validar_sql(sql).strip().endswith(";") is False


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT ticket FROM services;",
        "SELECT\n    ticket\nFROM services;",
        "SELECT\n    ticket,\n    status\nFROM services;",
        "SELECT\n\tticket\nFROM services;",
        "SELECT\t ticket FROM services;",
        "WITH recentes AS (\n    SELECT ticket FROM services\n)\nSELECT * FROM recentes;",
        "WITH\nrecentes AS (\n    SELECT ticket FROM services\n)\nSELECT * FROM recentes;",
    ],
)
def test_select_e_with_aceitam_whitespace_apos_palavra_chave(sql):
    assert validar_sql(sql).startswith(("SELECT", "WITH"))


def test_sql_multiline_real_do_n8n_e_aceito():
    sql = """SELECT
    ticket,
    status,
    store_name,
    praca,
    category,
    subcategory,
    created_on,
    analyst_responsible,
    supplier
FROM services
WHERE LOWER(BTRIM(praca)) = LOWER(BTRIM('natal'))
  AND status IN ('Em Aberto', 'Em atendimento')
ORDER BY ticket;
"""

    assert validar_sql(sql).startswith("SELECT")


def test_tabela_nao_permitida_e_bloqueada():
    with pytest.raises(ChatbotQueryError, match="users"):
        validar_sql("SELECT * FROM users")


def test_join_com_tabela_nao_permitida_e_bloqueado():
    sql = "SELECT * FROM services JOIN users ON users.id = services.id"

    with pytest.raises(ChatbotQueryError, match="users"):
        validar_sql(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO services (status) VALUES ('novo')",
        "UPDATE services SET status = 'novo'",
        "DELETE FROM services",
        "DROP TABLE services",
        "ALTER TABLE services ADD COLUMN extra text",
        "CREATE TABLE nova (id integer)",
    ],
)
def test_comandos_de_escrita_e_administracao_continuam_bloqueados(sql):
    with pytest.raises(ChatbotQueryError):
        validar_sql(sql)


def test_multiplas_instrucoes_continuam_bloqueadas():
    with pytest.raises(ChatbotQueryError, match="múltiplas instruções"):
        validar_sql("SELECT * FROM services; SELECT * FROM uploads")
