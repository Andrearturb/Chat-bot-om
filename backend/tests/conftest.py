"""
Fixtures compartilhadas para os testes do importer.

Usa SQLite em memória — sem dependência de PostgreSQL ou Docker.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.service import Service  # noqa: F401 — garante criação da tabela
from app.models.upload import Upload    # noqa: F401 — garante criação da tabela


@pytest.fixture(scope="function")
def db() -> Session:
    """Sessão SQLite em memória isolada por teste."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = SessionLocal()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def upload(db: Session) -> Upload:
    """Upload de controle pré-criado para uso nos testes."""
    u = Upload(source_file_name="test", total_rows=0)
    db.add(u)
    db.flush()
    return u


@pytest.fixture
def agora() -> datetime:
    return datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


def make_linha(
    ticket: str = "1001",
    status: str | None = "Em aberto",
    store_name: str | None = "Loja A | BCPS: 100 | SAP: 200",
    praca: str | None = "Nordeste",
    supplier: str | None = None,
    visit_date: str | None = None,
    in_attendance_date: str | None = None,
    service_description: str | None = "Descrição padrão",
    solution_text: str | None = None,
    signature_status: str | None = None,
    signed_pdf_url: str | None = None,
    created_on: str | None = None,  # None por padrão para evitar divergência com fixtures
    requester: str | None = None,
    analyst_responsible: str | None = None,
    non_approval_reason: str | None = None,
) -> dict:
    """Monta uma linha no formato já tratado pelo TapeTransformer."""
    return {
        "field_values": {
            "ticket":               {"field_id": 623225, "label": "Ticket",                        "value": ticket},
            "status":               {"field_id": 580453, "label": "Status",                        "value": status},
            "raw_location":         {"field_id": 580441, "label": "Local de Atendimento",          "value": store_name},
            "praca":                {"field_id": 580450, "label": "Praça",                         "value": praca},
            "service_description":  {"field_id": 638539, "label": "Descrição do Serviço",          "value": service_description},
            "supplier":             {"field_id": 603575, "label": "Fornecedor",                    "value": supplier},
            "visit_date":           {"field_id": 622874, "label": "Data da Visita",                "value": visit_date},
            "in_attendance_date":   {"field_id": 672479, "label": "data_inicio_atendimento",        "value": in_attendance_date},
            "solution_text":        {"field_id": 623224, "label": "Solução",                       "value": solution_text},
            "raw_signature":        {"field_id": 645992, "label": "Status da Assinatura",          "value": None},
            "requester":            {"field_id": 580436, "label": "Requisitante",                  "value": requester},
            "analyst_responsible":  {"field_id": 603645, "label": "Analista Responsável",          "value": analyst_responsible},
            "non_approval_reason":  {"field_id": 617502, "label": "Motivo da Não Aprovação",       "value": non_approval_reason},
        },
        "created_on": created_on,
    }
