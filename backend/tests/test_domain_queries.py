"""Os novos domínios usam suas próprias tabelas e mantêm o histórico de lojas."""

from datetime import date, datetime
from decimal import Decimal

from app.models.maintenance_cost import MaintenanceCost
from app.models.preventive_service import PreventiveService
from app.models.tape_center import TapeCenter
from app.schemas.domain_queries import CostQueryRequest, PreventiveQueryRequest
from app.services.cost_query import execute_cost_query
from app.services.preventive_query import execute_preventive_query


def center(db, upload, record_id, name, status="Aberta"):
    item = TapeCenter(record_id=record_id, title=name, name=name, praca="Natal",
                      status=status, upload_id=upload.id)
    db.add(item)
    db.flush()
    return item


def test_preventivas_contagem_lista_agrupamento_ranking_e_loja_fechada(db, upload):
    center(db, upload, 10, "Loja Fechada", "Fechada")
    db.add_all([
        PreventiveService(ticket="P1", status="Serviço Finalizado", periodicity="Mensal",
                          tape_center_record_id=10, category="Climatização", supplier="Fornecedor % Real",
                          created_on=datetime(2026, 8, 2), upload_id=upload.id),
        PreventiveService(ticket="P2", status="Backlog", periodicity="Mensal",
                          tape_center_record_id=10, category="Climatização", supplier="Fornecedor Normal",
                          created_on=datetime(2026, 8, 3), upload_id=upload.id),
        PreventiveService(ticket="P3", status="Backlog", periodicity="Anual",
                          created_on=datetime(2026, 9, 1), upload_id=upload.id),
    ])
    db.commit()
    base = {"session_id": "s", "access_token": "token", "query_shape": "count"}
    result = execute_preventive_query(db, PreventiveQueryRequest(**base, year=2026, month=8))
    assert result["total_count"] == 2
    result = execute_preventive_query(db, PreventiveQueryRequest(**base, status="Backlog", periodicity="Mensal"))
    assert result["total_count"] == 1
    result = execute_preventive_query(db, PreventiveQueryRequest(**base, supplier="%"))
    assert result["total_count"] == 1
    listing = execute_preventive_query(db, PreventiveQueryRequest(**{**base, "query_shape": "list"}, store_name="Fechada"))
    assert listing["total_count"] == 2 and listing["rows"][0]["ticket"] == "P2"
    grouped = execute_preventive_query(db, PreventiveQueryRequest(**{**base, "query_shape": "group"}, group_by="periodicity"))
    assert grouped["rows"][0] == {"label": "Mensal", "total": 2}
    ranking = execute_preventive_query(db, PreventiveQueryRequest(**{**base, "query_shape": "ranking"}, group_by="store_name"))
    assert ranking["rows"][0] == {"label": "Loja Fechada", "total": 2}


def test_custos_contagem_liquida_filtros_lista_agrupamento_e_loja_fechada(db, upload):
    center(db, upload, 10, "Loja Fechada", "Fechada")
    db.add_all([
        MaintenanceCost(upload_id=upload.id, conta_razao="41140014", posting_date=date(2026, 1, 2),
                        document_date=date(2025, 12, 29), amount=Decimal("100.00"), cost_center="CC1",
                        tape_center_record_id=10, supplier_name="Fornecedor % Real", document_number="D1"),
        MaintenanceCost(upload_id=upload.id, conta_razao="41140014", posting_date=date(2026, 1, 3),
                        amount=Decimal("-20.00"), cost_center="CC1", tape_center_record_id=10,
                        supplier_name="Fornecedor % Real", posting_key="91"),
        MaintenanceCost(upload_id=upload.id, conta_razao="41140026", posting_date=date(2026, 2, 1),
                        amount=Decimal("5.00"), cost_center="CC2"),
    ])
    db.commit()
    base = {"session_id": "s", "access_token": "token", "query_shape": "count"}
    result = execute_cost_query(db, CostQueryRequest(**base, conta_razao="41140014", year=2026, month=1))
    assert result["total_count"] == 2 and result["total_amount"] == "80.00"
    assert execute_cost_query(db, CostQueryRequest(**base, supplier="%"))["total_count"] == 2
    assert execute_cost_query(db, CostQueryRequest(**base, unattributed=True))["total_amount"] == "5.00"
    listing = execute_cost_query(db, CostQueryRequest(**{**base, "query_shape": "list"}, store_name="Fechada"))
    assert listing["total_count"] == 2 and listing["rows"][0]["amount"] == "-20.00"
    grouped = execute_cost_query(db, CostQueryRequest(**{**base, "query_shape": "group"}, group_by="conta_razao"))
    assert grouped["rows"][0]["total_amount"] == "80.00"
    ranking = execute_cost_query(db, CostQueryRequest(**{**base, "query_shape": "ranking"}, group_by="store_name"))
    assert ranking["rows"][0]["label"] == "Loja Fechada"
    unsupported = execute_cost_query(db, CostQueryRequest(**base, unsupported_filter="ar-condicionado"))
    assert unsupported["unsupported_filter"] == "ar-condicionado"
    assert unsupported["rows"] == []


def test_group_by_obrigatorio_somente_agrupamentos():
    import pytest
    from pydantic import ValidationError

    base = {"session_id": "s", "access_token": "token"}
    with pytest.raises(ValidationError):
        CostQueryRequest(**base, query_shape="group")
    with pytest.raises(ValidationError):
        PreventiveQueryRequest(**base, query_shape="count", group_by="status")
