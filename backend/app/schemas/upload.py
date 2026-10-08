"""
Schemas relacionados ao processo de sincronização.

Este módulo define o formato da resposta devolvida pela API após
a sincronização com a Tape API.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class UploadResponse(BaseModel):
    """
    Representa a resposta da API após uma sincronização concluída.

    Campos de contagem refletem o resultado efetivamente confirmado
    no banco — não operações planejadas.
    """

    message: str
    total_rows: int
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    rejected: int = 0
    upload_data: datetime | None
    source_file_name: str | None


class TapeSourceSyncResponse(BaseModel):
    app_id: int
    label: str
    status: Literal['success', 'empty', 'error']
    result: UploadResponse | None = None


class CentralSyncResponse(BaseModel):
    sources: list[TapeSourceSyncResponse]
