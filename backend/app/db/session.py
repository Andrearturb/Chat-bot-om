"""
Configuração da conexão com o banco de dados.

Este módulo cria o engine principal, define a fábrica de sessões
e disponibiliza a dependency `get_db` para injeção nas rotas da API.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import DATABASE_URL


# Engine compartilhado com toda a aplicação
engine = create_engine(DATABASE_URL)

# Fábrica de sessões — autocommit e autoflush desativados para controle explícito
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """
    Dependency do FastAPI que fornece uma sessão de banco por requisição.

    A sessão é aberta no início e fechada automaticamente ao final,
    independente de sucesso ou erro.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
