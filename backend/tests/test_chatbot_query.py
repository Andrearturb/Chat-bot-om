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
