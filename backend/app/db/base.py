"""
Base dos modelos do banco de dados.

Este módulo define a classe base utilizada pelo SQLAlchemy para que
as classes de modelo (models) possam ser interpretadas como tabelas
no banco de dados.
"""

from sqlalchemy.orm import declarative_base

# Classe base para todos os modelos do banco
Base = declarative_base()
