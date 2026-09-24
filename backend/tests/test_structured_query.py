from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models.service import Service
from app.models.upload import Upload
from app.schemas.structured_query import StructuredQueryRequest
from app.services.structured_query import (
    StructuredQueryError,
    build_structured_query,
    execute_structured_query,
)


@pytest.fixture
def structured_db() -> Session:
    engine = create_engine("sqlite:///:memory:")
    from app.db.base import Base

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    upload = Upload(source_file_name="structured-test", total_rows=5)
    session.add(upload)
    session.flush()

    rows = [
        dict(ticket="1001", status="Em atendimento", store_name="Loja A", praca="Natal", category="Elétrica", subcategory="Luz", service_description="Troca de luminária", analyst_responsible="Ana", supplier="Acme", requester="Rui", created_on=datetime(2026, 8, 1), completion_date=None, visit_date=datetime(2026, 8, 2)),
        dict(ticket="1002", status="Em Aberto", store_name="Loja A", praca="Natal", category="Elétrica", subcategory="Tomada", analyst_responsible="Ana", supplier=None, requester="Rui", created_on=datetime(2026, 8, 10), completion_date=None, visit_date=None),
        dict(ticket="1003", status="Concluído", store_name="Loja B", praca="Trairi", category="Civil", subcategory="Pintura", analyst_responsible="Bia", supplier="Beta", requester="Lia", created_on=datetime(2026, 8, 20), completion_date=datetime(2026, 8, 21), visit_date=datetime(2026, 8, 22)),
        dict(ticket="1004", status="Em atendimento", store_name="Trairi Central", praca="Fortaleza", category="Elétrica", subcategory="Luz", analyst_responsible="Bia", supplier=None, requester="Rui", created_on=datetime(2026, 7, 31), completion_date=None, visit_date=datetime(2026, 8, 5)),
        dict(ticket="1005", status="Pendente de aprovação", store_name="Loja C", praca="Natal", category=None, subcategory=None, analyst_responsible=None, supplier="Acme", requester="Lia", created_on=datetime(2026, 9, 1), completion_date=None, visit_date=None),
    ]
    for row in rows:
        session.add(Service(upload_id=upload.id, **row))
    session.commit()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


def request(query_shape: str, **state) -> StructuredQueryRequest:
    return StructuredQueryRequest(query_shape=query_shape, state=state)


def test_count_sem_filtros(structured_db):
    result = execute_structured_query(structured_db, request("count", event="current_status"))
    assert result["rows"] == [{"total": 5}]


def test_count_praca_e_status(structured_db):
    result = execute_structured_query(structured_db, request("count", event="current_status", praca="Natal", statuses=["Em atendimento"]))
    assert result["rows"] == [{"total": 1}]


def test_list_praca_statuses_multiplos(structured_db):
    result = execute_structured_query(structured_db, request("list", event="current_status", praca="Natal", statuses=["Em Aberto", "Em atendimento"]))
    assert [row["ticket"] for row in result["rows"]] == ["1001", "1002"]
    assert result["columns"] == [
        "ticket",
        "status",
        "created_on",
        "store_name",
        "praca",
        "category",
        "subcategory",
        "service_description",
        "completion_date",
        "visit_date",
        "analyst_responsible",
        "supplier",
        "requester",
    ]
    assert result["rows"][0]["service_description"] == "Troca de luminária"
    assert all("service_description" in row for row in result["rows"])


def test_location_term_aplica_store_ou_praca(structured_db):
    result = execute_structured_query(structured_db, request("count", event="current_status", location_term="Trairi"))
    assert result["rows"] == [{"total": 1}]


def test_filtros_textuais_e_classificacao(structured_db):
    result = execute_structured_query(structured_db, request("count", event="current_status", store_name="loja a", analyst_responsible="ana", supplier="acme", requester="rui", category="elétrica", subcategory="luz"))
    assert result["rows"] == [{"total": 1}]


def test_missing_field_supplier(structured_db):
    result = execute_structured_query(structured_db, request("count", event="current_status", missing_field="supplier"))
    assert result["rows"] == [{"total": 2}]


@pytest.mark.parametrize(
    ("event", "date_field"),
    [("opened", "created_on"), ("completed", "completion_date"), ("visited", "visit_date")],
)
def test_eventos_por_mes(structured_db, event, date_field):
    result = execute_structured_query(structured_db, request("count", event=event, date_field=date_field, year=2026, month=8))
    assert result["rows"] == [{"total": 3 if event == "opened" else 1 if event == "completed" else 3}]


def test_current_status_com_coorte_historica(structured_db):
    result = execute_structured_query(structured_db, request("count", event="current_status", date_field="created_on", year=2026, month=8, statuses=["Em atendimento"]))
    assert result["rows"] == [{"total": 1}]


def test_group_por_store_e_category(structured_db):
    store_result = execute_structured_query(structured_db, request("group", event="current_status", group_by="store_name"))
    category_result = execute_structured_query(structured_db, request("group", event="current_status", group_by="category"))
    assert store_result["rows"][0] == {"store_name": "Loja A", "total": 2}
    assert category_result["rows"][0] == {"category": "Elétrica", "total": 3}


def test_ranking_com_limite(structured_db):
    result = execute_structured_query(structured_db, request("ranking", event="current_status", statuses=["Em atendimento"], group_by="store_name", limit=5))
    assert result["rows"] == [{"store_name": "Loja A", "total": 1}, {"store_name": "Trairi Central", "total": 1}]


def test_year_sem_month_e_datas_inclusivas(structured_db):
    year_result = execute_structured_query(structured_db, request("count", event="opened", date_field="created_on", year=2026))
    range_result = execute_structured_query(structured_db, request("count", event="opened", date_field="created_on", start_date="2026-08-10", end_date="2026-08-20"))
    assert year_result["rows"] == [{"total": 5}]
    assert range_result["rows"] == [{"total": 2}]


def test_status_legado_quando_statuses_nulo(structured_db):
    result = execute_structured_query(structured_db, request("count", event="current_status", status="Concluído", statuses=None))
    assert result["rows"] == [{"total": 1}]


@pytest.mark.parametrize(
    "payload",
    [
        request("group", group_by=None),
        request("ranking", group_by="store_name", limit=None),
        request("count", missing_field="password"),
        request("count", group_by="services"),
        request("count", event="opened", date_field="completion_date", year=2026),
    ],
)
def test_estado_incompativel_rejeitado(payload):
    with pytest.raises(StructuredQueryError):
        build_structured_query(payload)


def test_status_invalido_rejeitado():
    with pytest.raises(StructuredQueryError, match="statuses inválidos"):
        build_structured_query(request("count", statuses=["Aberto OR 1=1"]))


def test_date_field_invalido_rejeitado_no_schema():
    with pytest.raises(ValueError):
        request("count", date_field="synced_at", year=2026)


def test_valor_com_apostrofo_e_injecao_sao_parametrizados(structured_db):
    payload = request("count", praca="Natal' OR 1=1 --")
    statement, _ = build_structured_query(payload)
    compiled = statement.compile(structured_db.get_bind())
    assert "Natal' OR 1=1 --" not in str(compiled)
    assert execute_structured_query(structured_db, payload)["rows"] == [{"total": 0}]


def test_list_tem_limite_de_seguranca(structured_db):
    result = execute_structured_query(structured_db, request("list"))
    assert result["truncated"] is False
    assert result["row_count"] == 5
