"""
Modelo da tabela de importações.

Este módulo define a estrutura da tabela responsável por armazenar
informações sobre cada sincronização realizada no sistema.

Campos de contagem (inseridos, atualizados, sem_alteracao) refletem
os resultados efetivamente confirmados no banco — não operações planejadas.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Upload(Base):
    """
    Representa um registro de sincronização com a Tape API.
    """

    __tablename__ = "uploads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    source_file_name: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )
    # Total de registros válidos recebidos e processados
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Contadores de resultado efetivo — populados após confirmação no banco
    inserted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unchanged_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
