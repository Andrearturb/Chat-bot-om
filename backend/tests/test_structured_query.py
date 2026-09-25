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


def test_list_limit_e_mais_recentes(structured_db):
    result = execute_structured_query(
        structured_db,
        request(
            "list",
            list_limit=3,
            sort_by="created_on",
            sort_order="desc",
        ),
    )

    assert [row["ticket"] for row in result["rows"]] == ["1005", "1003", "1002"]
    assert result["row_count"] == 3
    assert result["total_count"] == 5
    assert result["list_limit"] == 3
    assert result["sort_by"] == "created_on"
    assert result["sort_order"] == "desc"
    assert result["truncated"] is False


def test_list_limit_e_mais_antigos(structured_db):
    result = execute_structured_query(
        structured_db,
        request(
            "list",
            list_limit=2,
            sort_by="created_on",
            sort_order="asc",
        ),
    )

    assert [row["ticket"] for row in result["rows"]] == ["1004", "1001"]
    assert result["row_count"] == 2
    assert result["total_count"] == 5
    assert result["truncated"] is False


def test_list_sort_por_data_de_conclusao(structured_db):
    result = execute_structured_query(
        structured_db,
        request(
            "list",
            event="completed",
            date_field="completion_date",
            year=2026,
            list_limit=1,
            sort_by="completion_date",
            sort_order="desc",
        ),
    )

    assert [row["ticket"] for row in result["rows"]] == ["1003"]
    assert result["total_count"] == 1


def test_list_options_rejeitadas_fora_de_list():
    with pytest.raises(StructuredQueryError, match="só podem ser usados"):
        build_structured_query(
            request(
                "count",
                list_limit=10,
                sort_by="created_on",
                sort_order="desc",
            )
        )


def test_sort_order_exige_sort_by():
    with pytest.raises(StructuredQueryError, match="sort_order exige sort_by"):
        build_structured_query(request("list", sort_order="desc"))


def test_sort_by_exige_sort_order():
    with pytest.raises(StructuredQueryError, match="sort_by exige sort_order"):
        build_structured_query(request("list", sort_by="created_on"))


def comparison_request(dimension: str, items: list[dict], **state) -> StructuredQueryRequest:
    return StructuredQueryRequest(
        query_shape="comparison",
        state=state,
        comparison={"dimension": dimension, "items": items},
    )


def test_comparison_periodos_calcula_diferenca_e_percentual(structured_db):
    result = execute_structured_query(
        structured_db,
        comparison_request(
            "period",
            [
                {"label": "Julho de 2026", "year": 2026, "month": 7},
                {"label": "Agosto de 2026", "year": 2026, "month": 8},
            ],
            event="opened",
            date_field="created_on",
        ),
    )

    assert result["rows"] == [
        {"label": "Julho de 2026", "total": 1},
        {"label": "Agosto de 2026", "total": 3},
    ]
    assert result["comparison"] == {
        "dimension": "period",
        "base_label": "Julho de 2026",
        "target_label": "Agosto de 2026",
        "difference": 2,
        "percentage_change": 200.0,
        "direction": "increase",
    }


def test_comparison_pracas_preserva_filtro_comum_de_status(structured_db):
    result = execute_structured_query(
        structured_db,
        comparison_request(
            "praca",
            [
                {"label": "Natal", "value": "Natal"},
                {"label": "Fortaleza", "value": "Fortaleza"},
            ],
            event="current_status",
            statuses=["Em atendimento"],
        ),
    )

    assert result["rows"] == [
        {"label": "Natal", "total": 1},
        {"label": "Fortaleza", "total": 1},
    ]
    assert result["comparison"]["difference"] == 0
    assert result["comparison"]["percentage_change"] == 0.0
    assert result["comparison"]["direction"] == "stable"


def test_comparison_statuses_forca_status_atual(structured_db):
    result = execute_structured_query(
        structured_db,
        comparison_request(
            "status",
            [
                {"label": "Em Aberto", "value": "Em Aberto"},
                {"label": "Concluído", "value": "Concluído"},
            ],
        ),
    )

    assert result["rows"] == [
        {"label": "Em Aberto", "total": 1},
        {"label": "Concluído", "total": 1},
    ]


def test_comparison_percentual_nulo_quando_base_zero(structured_db):
    result = execute_structured_query(
        structured_db,
        comparison_request(
            "praca",
            [
                {"label": "Inexistente", "value": "Inexistente"},
                {"label": "Natal", "value": "Natal"},
            ],
            event="current_status",
        ),
    )

    assert result["comparison"]["difference"] == 3
    assert result["comparison"]["percentage_change"] is None
    assert result["comparison"]["direction"] == "increase"


def test_comparison_periodo_exige_date_field():
    payload = comparison_request(
        "period",
        [
            {"year": 2026, "month": 7},
            {"year": 2026, "month": 8},
        ],
    )

    with pytest.raises(StructuredQueryError, match="exige date_field"):
        execute_structured_query(None, payload)


def test_comparison_exige_exatamente_dois_itens_no_schema():
    with pytest.raises(ValueError):
        comparison_request(
            "praca",
            [{"label": "Natal", "value": "Natal"}],
            event="current_status",
        )


def test_comparison_breakdown_por_loja_ordena_maiores_reducoes(structured_db):
    payload = StructuredQueryRequest(
        query_shape="comparison",
        state={"event": "opened", "date_field": "created_on"},
        comparison={
            "dimension": "period",
            "items": [
                {"label": "Julho de 2026", "year": 2026, "month": 7},
                {"label": "Agosto de 2026", "year": 2026, "month": 8},
            ],
            "breakdown_by": "store_name",
            "breakdown_order": "decrease",
            "breakdown_limit": 5,
        },
    )

    result = execute_structured_query(structured_db, payload)

    assert result["comparison"]["breakdown_by"] == "store_name"
    assert result["comparison"]["breakdown_order"] == "decrease"
    assert result["breakdown"] == [
        {
            "label": "Trairi Central",
            "base_total": 1,
            "target_total": 0,
            "difference": -1,
            "percentage_change": -100.0,
            "direction": "decrease",
        }
    ]


def test_comparison_breakdown_maior_variacao_com_limite(structured_db):
    payload = StructuredQueryRequest(
        query_shape="comparison",
        state={"event": "opened", "date_field": "created_on"},
        comparison={
            "dimension": "period",
            "items": [
                {"label": "Julho de 2026", "year": 2026, "month": 7},
                {"label": "Agosto de 2026", "year": 2026, "month": 8},
            ],
            "breakdown_by": "store_name",
            "breakdown_order": "absolute_change",
            "breakdown_limit": 1,
        },
    )

    result = execute_structured_query(structured_db, payload)

    assert result["breakdown"] == [
        {
            "label": "Loja A",
            "base_total": 0,
            "target_total": 2,
            "difference": 2,
            "percentage_change": None,
            "direction": "increase",
        }
    ]


def test_comparison_breakdown_rejeita_mesma_dimensao(structured_db):
    payload = StructuredQueryRequest(
        query_shape="comparison",
        state={"event": "current_status"},
        comparison={
            "dimension": "praca",
            "items": [
                {"label": "Natal", "value": "Natal"},
                {"label": "Fortaleza", "value": "Fortaleza"},
            ],
            "breakdown_by": "praca",
            "breakdown_order": "absolute_change",
        },
    )

    with pytest.raises(StructuredQueryError, match="não pode repetir"):
        execute_structured_query(structured_db, payload)


def test_comparison_breakdown_order_exige_breakdown_by(structured_db):
    payload = StructuredQueryRequest(
        query_shape="comparison",
        state={"event": "opened", "date_field": "created_on"},
        comparison={
            "dimension": "period",
            "items": [
                {"label": "Julho de 2026", "year": 2026, "month": 7},
                {"label": "Agosto de 2026", "year": 2026, "month": 8},
            ],
            "breakdown_order": "decrease",
        },
    )

    with pytest.raises(StructuredQueryError, match="exigem comparison.breakdown_by"):
        execute_structured_query(structured_db, payload)


def test_comparison_drivers_padrao_decompoe_categoria_e_loja(structured_db):
    payload = StructuredQueryRequest(
        query_shape="comparison",
        state={"event": "opened", "date_field": "created_on"},
        comparison={
            "dimension": "period",
            "items": [
                {"label": "Julho de 2026", "year": 2026, "month": 7},
                {"label": "Agosto de 2026", "year": 2026, "month": 8},
            ],
            "analysis_mode": "drivers",
        },
    )

    result = execute_structured_query(structured_db, payload)

    assert result["comparison"]["analysis_mode"] == "drivers"
    assert result["comparison"]["driver_dimensions"] == ["category", "store_name"]
    assert result["comparison"]["driver_limit"] == 3

    analysis = result["driver_analysis"]
    assert analysis["mode"] == "drivers"
    assert analysis["net_difference"] == 2
    assert analysis["direction"] == "increase"

    category = analysis["dimensions"][0]
    assert category["dimension"] == "category"
    assert category["gross_driver_change"] == 2
    assert category["gross_offset_change"] == 0
    assert category["top_drivers"] == [
        {
            "label": "Civil",
            "base_total": 0,
            "target_total": 1,
            "difference": 1,
            "percentage_change": None,
            "direction": "increase",
            "contribution_pct": 50.0,
        },
        {
            "label": "Elétrica",
            "base_total": 1,
            "target_total": 2,
            "difference": 1,
            "percentage_change": 100.0,
            "direction": "increase",
            "contribution_pct": 50.0,
        },
    ]

    store = analysis["dimensions"][1]
    assert store["dimension"] == "store_name"
    assert store["gross_driver_change"] == 3
    assert store["gross_offset_change"] == 1
    assert store["top_drivers"][0]["label"] == "Loja A"
    assert store["top_drivers"][0]["difference"] == 2
    assert store["top_drivers"][0]["contribution_pct"] == 100.0
    assert store["offsets"] == [
        {
            "label": "Trairi Central",
            "base_total": 1,
            "target_total": 0,
            "difference": -1,
            "percentage_change": -100.0,
            "direction": "decrease",
            "contribution_pct": -50.0,
        }
    ]


def test_comparison_drivers_respeita_dimensao_e_limite(structured_db):
    payload = StructuredQueryRequest(
        query_shape="comparison",
        state={"event": "opened", "date_field": "created_on"},
        comparison={
            "dimension": "period",
            "items": [
                {"label": "Julho de 2026", "year": 2026, "month": 7},
                {"label": "Agosto de 2026", "year": 2026, "month": 8},
            ],
            "analysis_mode": "drivers",
            "driver_dimensions": ["store_name"],
            "driver_limit": 1,
        },
    )

    result = execute_structured_query(structured_db, payload)
    analysis = result["driver_analysis"]

    assert result["comparison"]["driver_dimensions"] == ["store_name"]
    assert result["comparison"]["driver_limit"] == 1
    assert len(analysis["dimensions"]) == 1
    assert len(analysis["dimensions"][0]["top_drivers"]) == 1
    assert len(analysis["dimensions"][0]["offsets"]) == 1


def test_comparison_drivers_estavel_mostra_movimentos_sem_contribuicao(structured_db):
    payload = StructuredQueryRequest(
        query_shape="comparison",
        state={"event": "current_status", "statuses": ["Em atendimento"]},
        comparison={
            "dimension": "praca",
            "items": [
                {"label": "Natal", "value": "Natal"},
                {"label": "Fortaleza", "value": "Fortaleza"},
            ],
            "analysis_mode": "drivers",
            "driver_dimensions": ["store_name"],
        },
    )

    result = execute_structured_query(structured_db, payload)
    analysis = result["driver_analysis"]

    assert analysis["net_difference"] == 0
    assert analysis["direction"] == "stable"
    assert all(
        row["contribution_pct"] is None
        for row in analysis["dimensions"][0]["top_drivers"]
    )


def test_comparison_drivers_rejeita_breakdown_simultaneo(structured_db):
    payload = StructuredQueryRequest(
        query_shape="comparison",
        state={"event": "opened", "date_field": "created_on"},
        comparison={
            "dimension": "period",
            "items": [
                {"label": "Julho de 2026", "year": 2026, "month": 7},
                {"label": "Agosto de 2026", "year": 2026, "month": 8},
            ],
            "breakdown_by": "category",
            "analysis_mode": "drivers",
            "driver_dimensions": ["category"],
        },
    )

    with pytest.raises(StructuredQueryError, match="não deve ser combinado"):
        execute_structured_query(structured_db, payload)


def test_multi_filters_store_name_funciona_com_or(structured_db):
    result = execute_structured_query(
        structured_db,
        request(
            "list",
            event="current_status",
            multi_filters={"store_name": ["Loja A", "Loja B"]},
        ),
    )

    assert [row["ticket"] for row in result["rows"]] == ["1001", "1002", "1003"]


def test_multi_filters_combinam_dimensoes_com_and(structured_db):
    result = execute_structured_query(
        structured_db,
        request(
            "list",
            event="current_status",
            multi_filters={
                "category": ["Elétrica", "Civil"],
                "supplier": ["Acme", "Beta"],
            },
        ),
    )

    assert [row["ticket"] for row in result["rows"]] == ["1001", "1003"]


def test_contextual_selection_top_driver_vira_filtro_multiplo(structured_db):
    payload = StructuredQueryRequest(
        query_shape="list",
        state={"event": "opened", "date_field": "created_on"},
        selection_context={
            "source": "previous_comparison",
            "mode": "top_drivers",
            "dimension": "store_name",
            "limit": 1,
            "source_state": {"event": "opened", "date_field": "created_on"},
            "source_comparison": {
                "dimension": "period",
                "items": [
                    {"label": "Julho de 2026", "year": 2026, "month": 7},
                    {"label": "Agosto de 2026", "year": 2026, "month": 8},
                ],
                "analysis_mode": "drivers",
                "driver_dimensions": ["store_name"],
                "driver_limit": 1,
            },
        },
    )

    result = execute_structured_query(structured_db, payload)

    assert [row["ticket"] for row in result["rows"]] == ["1001", "1002"]
    assert result["resolved_selection"] == {
        "source": "previous_comparison",
        "mode": "top_drivers",
        "dimension": "store_name",
        "values": ["Loja A"],
        "inherited_comparison_scope": True,
    }


def test_contextual_selection_offsets_preserva_escopo_da_comparacao(structured_db):
    payload = StructuredQueryRequest(
        query_shape="list",
        state={"event": "opened", "date_field": "created_on"},
        selection_context={
            "source": "previous_comparison",
            "mode": "offsets",
            "dimension": "store_name",
            "limit": 1,
            "source_state": {"event": "opened", "date_field": "created_on"},
            "source_comparison": {
                "dimension": "period",
                "items": [
                    {"label": "Julho de 2026", "year": 2026, "month": 7},
                    {"label": "Agosto de 2026", "year": 2026, "month": 8},
                ],
                "analysis_mode": "drivers",
                "driver_dimensions": ["store_name"],
                "driver_limit": 1,
            },
        },
    )

    result = execute_structured_query(structured_db, payload)

    assert [row["ticket"] for row in result["rows"]] == ["1004"]
    assert result["resolved_selection"]["values"] == ["Trairi Central"]


def test_contextual_selection_breakdown_reutiliza_resultado_anterior(structured_db):
    payload = StructuredQueryRequest(
        query_shape="count",
        state={"event": "opened", "date_field": "created_on"},
        selection_context={
            "source": "previous_comparison",
            "mode": "breakdown",
            "dimension": "store_name",
            "limit": 1,
            "source_state": {"event": "opened", "date_field": "created_on"},
            "source_comparison": {
                "dimension": "period",
                "items": [
                    {"label": "Julho de 2026", "year": 2026, "month": 7},
                    {"label": "Agosto de 2026", "year": 2026, "month": 8},
                ],
                "breakdown_by": "store_name",
                "breakdown_order": "decrease",
                "breakdown_limit": 1,
            },
        },
    )

    result = execute_structured_query(structured_db, payload)

    assert result["rows"] == [{"total": 1}]
    assert result["resolved_selection"]["values"] == ["Trairi Central"]


def test_contextual_selection_comparison_items(structured_db):
    payload = StructuredQueryRequest(
        query_shape="count",
        state={"event": "current_status"},
        selection_context={
            "source": "previous_comparison",
            "mode": "comparison_items",
            "dimension": "praca",
            "source_state": {"event": "current_status"},
            "source_comparison": {
                "dimension": "praca",
                "items": [
                    {"label": "Natal", "value": "Natal"},
                    {"label": "Fortaleza", "value": "Fortaleza"},
                ],
            },
        },
    )

    result = execute_structured_query(structured_db, payload)

    assert result["rows"] == [{"total": 4}]
    assert result["resolved_selection"]["values"] == ["Natal", "Fortaleza"]


def test_drilldown_explicit_category_filter_with_store_breakdown(structured_db):
    """Preserva a comparação e aprofunda uma categoria por loja."""
    payload = StructuredQueryRequest(
        query_shape="comparison",
        state={
            "event": "opened",
            "date_field": "created_on",
            "category": "Elétrica",
        },
        comparison={
            "dimension": "period",
            "items": [
                {"label": "Julho de 2026", "year": 2026, "month": 7},
                {"label": "Agosto de 2026", "year": 2026, "month": 8},
            ],
            "breakdown_by": "store_name",
            "breakdown_order": "increase",
            "breakdown_limit": 5,
        },
    )

    result = execute_structured_query(structured_db, payload)

    assert result["rows"] == [
        {"label": "Julho de 2026", "total": 1},
        {"label": "Agosto de 2026", "total": 2},
    ]
    assert result["comparison"]["breakdown_by"] == "store_name"
    assert result["comparison"]["breakdown_order"] == "increase"
    assert result["breakdown"] == [
        {
            "label": "Loja A",
            "base_total": 0,
            "target_total": 2,
            "difference": 2,
            "percentage_change": None,
            "direction": "increase",
        }
    ]


def test_drilldown_contextual_top_category_then_breakdown_by_store(structured_db):
    """Permite usar a primeira categoria driver como filtro e aprofundar por loja."""
    payload = StructuredQueryRequest(
        query_shape="comparison",
        state={"event": "opened", "date_field": "created_on"},
        comparison={
            "dimension": "period",
            "items": [
                {"label": "Julho de 2026", "year": 2026, "month": 7},
                {"label": "Agosto de 2026", "year": 2026, "month": 8},
            ],
            "breakdown_by": "store_name",
            "breakdown_order": "increase",
            "breakdown_limit": 5,
        },
        selection_context={
            "source": "previous_comparison",
            "mode": "top_drivers",
            "dimension": "category",
            "limit": 1,
            "source_state": {"event": "opened", "date_field": "created_on"},
            "source_comparison": {
                "dimension": "period",
                "items": [
                    {"label": "Julho de 2026", "year": 2026, "month": 7},
                    {"label": "Agosto de 2026", "year": 2026, "month": 8},
                ],
                "analysis_mode": "drivers",
                "driver_dimensions": ["category"],
                "driver_limit": 3,
            },
        },
    )

    result = execute_structured_query(structured_db, payload)

    assert result["resolved_selection"]["dimension"] == "category"
    assert result["resolved_selection"]["values"] == ["Civil"]
    assert result["rows"] == [
        {"label": "Julho de 2026", "total": 0},
        {"label": "Agosto de 2026", "total": 1},
    ]
    assert result["breakdown"] == [
        {
            "label": "Loja B",
            "base_total": 0,
            "target_total": 1,
            "difference": 1,
            "percentage_change": None,
            "direction": "increase",
        }
    ]
