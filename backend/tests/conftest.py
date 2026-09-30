"""
Fixtures compartilhadas para os testes.
Usa SQLite em memória — sem dependência de PostgreSQL ou Docker.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base

from app.models.service import Service          # noqa: F401
from app.models.upload import Upload            # noqa: F401
from app.models.asset_store import AssetStore   # noqa: F401
from app.models.climate_asset import ClimateAsset  # noqa: F401
from app.models.fire_asset import FireAsset     # noqa: F401
from app.models.store_document import StoreDocument  # noqa: F401
from app.models.water_asset import WaterAsset   # noqa: F401
from app.models.auth import (                   # noqa: F401
    Profile, Permission, ProfilePermission,
    AppUser, OidcIdentity, UserSession,
    UserPermissionOverride, AssistantConversation,
    AssistantMessage, AiUsage, AuditLog, SecurityEvent,
)


@pytest.fixture(scope="function")
def db() -> Session:
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
    u = Upload(source_file_name="test", total_rows=0)
    db.add(u)
    db.flush()
    return u


@pytest.fixture
def agora() -> datetime:
    return datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


def make_linha(
    ticket="1001", status="Em aberto",
    store_name="Loja A | BCPS: 100 | SAP: 200", praca="Nordeste",
    supplier=None, visit_date=None, in_attendance_date=None,
    service_description="Descrição padrão", solution_text=None,
    signature_status=None, signed_pdf_url=None, created_on=None,
    requester=None, analyst_responsible=None, non_approval_reason=None,
) -> dict:
    return {
        "field_values": {
            "ticket":               {"field_id": 623225, "label": "Ticket",                     "value": ticket},
            "status":               {"field_id": 580453, "label": "Status",                     "value": status},
            "raw_location":         {"field_id": 580441, "label": "Local de Atendimento",       "value": store_name},
            "praca":                {"field_id": 580450, "label": "Praça",                      "value": praca},
            "service_description":  {"field_id": 638539, "label": "Descrição do Serviço",       "value": service_description},
            "supplier":             {"field_id": 603575, "label": "Fornecedor",                 "value": supplier},
            "visit_date":           {"field_id": 622874, "label": "Data da Visita",             "value": visit_date},
            "in_attendance_date":   {"field_id": 672479, "label": "data_inicio_atendimento",    "value": in_attendance_date},
            "solution_text":        {"field_id": 623224, "label": "Solução",                    "value": solution_text},
            "raw_signature":        {"field_id": 645992, "label": "Status da Assinatura",       "value": None},
            "requester":            {"field_id": 580436, "label": "Requisitante",               "value": requester},
            "analyst_responsible":  {"field_id": 603645, "label": "Analista Responsável",       "value": analyst_responsible},
            "non_approval_reason":  {"field_id": 617502, "label": "Motivo da Não Aprovação",    "value": non_approval_reason},
        },
        "created_on": created_on,
    }


@pytest.fixture
def provider(monkeypatch):
    """Keycloak simulado instalado no app (config + transporte HTTP do módulo oidc)."""
    from app.services import oidc
    from tests.oidc_fake import FakeProvider, install

    fake = FakeProvider()
    install(monkeypatch, fake)
    yield fake
    oidc.reset_cache()
