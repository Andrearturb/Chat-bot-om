from pydantic import BaseModel, Field


class ChatbotQueryRequest(BaseModel):
    sql: str = Field(
        ...,
        min_length=1,
        description="Consulta SQL somente leitura gerada pelo agente de IA.",
    )
    qa_trace_id: str | None = Field(
        default=None,
        max_length=255,
        description="Identificador opcional do trace de QA para registrar a execução.",
    )


class ChatbotQueryResponse(BaseModel):
    success: bool
    row_count: int
    truncated: bool
    columns: list[str]
    rows: list[dict]