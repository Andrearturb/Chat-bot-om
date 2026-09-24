from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import Select, and_, asc, desc, func, or_, select
from sqlalchemy.orm import Session

from app.models.service import Service
from app.schemas.structured_query import (
    BREAKDOWN_DIMENSIONS,
    BREAKDOWN_ORDERS,
    COMPARISON_DIMENSIONS,
    QUERY_SHAPES,
    ComparisonItem,
    ComparisonSpec,
    SelectionContextSpec,
    StructuredQueryRequest,
    StructuredQueryState,
)

MAX_LIST_ROWS = 200
DEFAULT_DRIVER_DIMENSIONS = ("category", "store_name")
DEFAULT_DRIVER_LIMIT = 3
CANONICAL_STATUSES = {
    "Em Aberto",
    "Em atendimento",
    "Pendente de aprovação",
    "Não Aprovado",
    "Concluído",
}

TEXT_FIELDS = {
    "praca": Service.praca,
    "store_name": Service.store_name,
    "analyst_responsible": Service.analyst_responsible,
    "supplier": Service.supplier,
    "requester": Service.requester,
    "category": Service.category,
    "subcategory": Service.subcategory,
}
DATE_FIELDS = {
    "created_on": Service.created_on,
    "completion_date": Service.completion_date,
    "visit_date": Service.visit_date,
}
GROUP_FIELDS = {
    **TEXT_FIELDS,
    "status": Service.status,
}
LIST_FIELDS = (
    Service.ticket,
    Service.status,
    Service.created_on,
    Service.store_name,
    Service.praca,
    Service.category,
    Service.subcategory,
    Service.service_description,
    Service.completion_date,
    Service.visit_date,
    Service.analyst_responsible,
    Service.supplier,
    Service.requester,
)
EVENT_DATE_FIELDS = {
    "opened": "created_on",
    "completed": "completion_date",
    "visited": "visit_date",
}

PORTUGUESE_MONTHS = {
    1: "Janeiro",
    2: "Fevereiro",
    3: "Março",
    4: "Abril",
    5: "Maio",
    6: "Junho",
    7: "Julho",
    8: "Agosto",
    9: "Setembro",
    10: "Outubro",
    11: "Novembro",
    12: "Dezembro",
}


class StructuredQueryError(ValueError):
    pass


def _exact_text(column: Any, value: str) -> Any:
    return func.lower(func.trim(column)) == func.lower(func.trim(value))


def _text_values_predicate(column: Any, values: list[str]) -> Any:
    """Case-insensitive OR match for multiple text values.

    The synthetic label "Não informado" also matches NULL/blank values so
    contextual selections can reuse labels produced by grouped analyses.
    """

    regular_values: list[str] = []
    include_missing = False

    for raw_value in values:
        value = str(raw_value).strip()
        if not value:
            continue

        if value.casefold() == "não informado".casefold():
            include_missing = True
            continue

        regular_values.append(value)

    predicates: list[Any] = []

    if regular_values:
        predicates.append(or_(*[_exact_text(column, value) for value in regular_values]))

    if include_missing:
        predicates.append(or_(column.is_(None), func.trim(column) == ""))

    if not predicates:
        # A predicate that is always false is safer than accidentally removing
        # the filter when an empty selection reaches the backend.
        return column.is_(None) & (column.is_not(None))

    return or_(*predicates)


def _location_values_predicate(values: list[str]) -> Any:
    return or_(
        _text_values_predicate(Service.store_name, values),
        _text_values_predicate(Service.praca, values),
    )


def _parse_date(value: date | datetime, field_name: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raise StructuredQueryError(f"{field_name} deve ser uma data válida.")


def _next_month(year: int, month: int) -> date:
    return date(year + (month == 12), 1 if month == 12 else month + 1, 1)


def _validate_state(query_shape: str, state: StructuredQueryState) -> None:
    if query_shape not in QUERY_SHAPES:
        raise StructuredQueryError(
            "query_shape inválido: "
            f"{query_shape}. Use count, list, group, ranking ou comparison."
        )

    if state.statuses is not None:
        invalid = [status for status in state.statuses if status not in CANONICAL_STATUSES]
        if invalid:
            raise StructuredQueryError(f"statuses inválidos: {invalid}.")

    if state.status is not None and state.status not in CANONICAL_STATUSES:
        raise StructuredQueryError(f"status inválido: {state.status}.")

    if state.missing_field is not None and state.missing_field not in TEXT_FIELDS:
        raise StructuredQueryError(
            f"missing_field inválido: {state.missing_field}."
        )

    if state.group_by is not None and state.group_by not in GROUP_FIELDS:
        raise StructuredQueryError(f"group_by inválido: {state.group_by}.")

    if query_shape in {"group", "ranking"} and state.group_by is None:
        raise StructuredQueryError(f"{query_shape} exige group_by.")

    if query_shape == "ranking" and state.limit is None:
        raise StructuredQueryError("ranking exige limit.")

    if state.start_date and state.end_date:
        if _parse_date(state.end_date, "end_date") < _parse_date(
            state.start_date, "start_date"
        ):
            raise StructuredQueryError("end_date não pode ser anterior a start_date.")

    if state.year is not None and state.month is None and not 1 <= state.year <= 9999:
        raise StructuredQueryError("year deve estar entre 1 e 9999.")

    expected_date_field = EVENT_DATE_FIELDS.get(state.event)
    if expected_date_field and state.date_field != expected_date_field:
        raise StructuredQueryError(
            f"event={state.event} exige date_field={expected_date_field}."
        )


def _validate_comparison_item(dimension: str, item: ComparisonItem, position: int) -> None:
    prefix = f"comparison.items[{position}]"

    if dimension == "period":
        has_calendar_period = item.year is not None or item.month is not None
        has_date_range = item.start_date is not None or item.end_date is not None

        if not has_calendar_period and not has_date_range:
            raise StructuredQueryError(
                f"{prefix} deve informar year/month ou start_date/end_date para comparação por período."
            )

        if item.month is not None and item.year is None:
            raise StructuredQueryError(f"{prefix}.month exige year.")

        if item.start_date and item.end_date:
            if _parse_date(item.end_date, f"{prefix}.end_date") < _parse_date(
                item.start_date, f"{prefix}.start_date"
            ):
                raise StructuredQueryError(
                    f"{prefix}.end_date não pode ser anterior a start_date."
                )
        return

    if item.value is None or not item.value.strip():
        raise StructuredQueryError(
            f"{prefix}.value é obrigatório para comparação por {dimension}."
        )

    if dimension == "status" and item.value not in CANONICAL_STATUSES:
        raise StructuredQueryError(
            f"{prefix}.value contém status inválido: {item.value}."
        )


def _validate_comparison(
    query_shape: str,
    state: StructuredQueryState,
    comparison: ComparisonSpec | None,
) -> None:
    if query_shape != "comparison":
        return

    if comparison is None:
        raise StructuredQueryError("comparison é obrigatório quando query_shape=comparison.")

    if comparison.dimension not in COMPARISON_DIMENSIONS:
        raise StructuredQueryError(
            f"comparison.dimension inválido: {comparison.dimension}."
        )

    if len(comparison.items) != 2:
        raise StructuredQueryError("comparison exige exatamente dois itens.")

    if comparison.dimension == "period" and state.date_field is None:
        raise StructuredQueryError(
            "comparison por período exige date_field no estado comum."
        )

    if comparison.breakdown_by is not None:
        if comparison.breakdown_by not in BREAKDOWN_DIMENSIONS:
            raise StructuredQueryError(
                f"comparison.breakdown_by inválido: {comparison.breakdown_by}."
            )
        if comparison.breakdown_by == comparison.dimension:
            raise StructuredQueryError(
                "comparison.breakdown_by não pode repetir a dimensão comparada."
            )
    elif comparison.breakdown_order is not None or comparison.breakdown_limit is not None:
        raise StructuredQueryError(
            "breakdown_order/breakdown_limit exigem comparison.breakdown_by."
        )

    if (
        comparison.breakdown_order is not None
        and comparison.breakdown_order not in BREAKDOWN_ORDERS
    ):
        raise StructuredQueryError(
            f"comparison.breakdown_order inválido: {comparison.breakdown_order}."
        )

    if comparison.analysis_mode is None:
        if comparison.driver_dimensions is not None or comparison.driver_limit is not None:
            raise StructuredQueryError(
                "driver_dimensions/driver_limit exigem comparison.analysis_mode=drivers."
            )
    elif comparison.analysis_mode == "drivers":
        if comparison.breakdown_by is not None:
            raise StructuredQueryError(
                "analysis_mode=drivers não deve ser combinado com comparison.breakdown_by."
            )

        if comparison.driver_dimensions is not None:
            for dimension in comparison.driver_dimensions:
                if dimension not in BREAKDOWN_DIMENSIONS:
                    raise StructuredQueryError(
                        f"driver dimension inválida: {dimension}."
                    )
                if dimension == comparison.dimension:
                    raise StructuredQueryError(
                        "driver_dimensions não pode repetir a dimensão comparada."
                    )

    for index, item in enumerate(comparison.items):
        _validate_comparison_item(comparison.dimension, item, index)


def _date_predicates(state: StructuredQueryState) -> list[Any]:
    if state.date_field is None:
        if state.year is not None or state.month is not None or state.start_date or state.end_date:
            raise StructuredQueryError(
                "date_field é obrigatório quando filtros de data são informados."
            )
        return []

    column = DATE_FIELDS[state.date_field]
    predicates: list[Any] = []

    if state.month is not None and state.year is None:
        raise StructuredQueryError("month exige year.")

    if state.year is not None:
        start = date(state.year, state.month or 1, 1)
        end = (
            _next_month(state.year, state.month)
            if state.month
            else date(state.year + 1, 1, 1)
        )
        predicates.extend((column >= start, column < end))

    if state.start_date is not None:
        predicates.append(column >= _parse_date(state.start_date, "start_date"))

    if state.end_date is not None:
        end_inclusive = _parse_date(state.end_date, "end_date")
        predicates.append(column < end_inclusive + timedelta(days=1))

    return predicates


def _build_predicates(state: StructuredQueryState) -> list[Any]:
    predicates = _date_predicates(state)

    for field_name, column in TEXT_FIELDS.items():
        field_value = getattr(state, field_name)
        if field_value is not None:
            predicates.append(_exact_text(column, field_value))

    if state.location_term is not None:
        predicates.append(
            or_(
                _exact_text(Service.store_name, state.location_term),
                _exact_text(Service.praca, state.location_term),
            )
        )

    statuses = state.statuses
    if statuses is None and state.status is not None:
        statuses = [state.status]
    if statuses:
        predicates.append(Service.status.in_(statuses))

    if state.multi_filters is not None:
        multi_filters = state.multi_filters.model_dump(exclude_none=True)

        for dimension, values in multi_filters.items():
            if not values:
                continue

            if dimension == "location_term":
                predicates.append(_location_values_predicate(values))
                continue

            column = TEXT_FIELDS.get(dimension)
            if column is None:
                raise StructuredQueryError(
                    f"multi_filters contém dimensão inválida: {dimension}."
                )

            predicates.append(_text_values_predicate(column, values))

    if state.missing_field is not None:
        column = TEXT_FIELDS[state.missing_field]
        predicates.append(or_(column.is_(None), func.trim(column) == ""))

    return predicates


def _label_for_comparison_item(dimension: str, item: ComparisonItem) -> str:
    if item.label and item.label.strip():
        return item.label.strip()

    if dimension != "period":
        return (item.value or "Item").strip()

    if item.year is not None and item.month is not None:
        month_name = PORTUGUESE_MONTHS.get(item.month, str(item.month))
        return f"{month_name} de {item.year}"

    if item.year is not None:
        return str(item.year)

    if item.start_date is not None and item.end_date is not None:
        start = _parse_date(item.start_date, "start_date").strftime("%d/%m/%Y")
        end = _parse_date(item.end_date, "end_date").strftime("%d/%m/%Y")
        return f"{start} a {end}"

    if item.start_date is not None:
        start = _parse_date(item.start_date, "start_date").strftime("%d/%m/%Y")
        return f"A partir de {start}"

    if item.end_date is not None:
        end = _parse_date(item.end_date, "end_date").strftime("%d/%m/%Y")
        return f"Até {end}"

    return "Período"


def _state_for_comparison_item(
    base_state: StructuredQueryState,
    dimension: str,
    item: ComparisonItem,
) -> StructuredQueryState:
    data = base_state.model_dump()

    # Estrutura de group/ranking não participa de comparação de totais.
    data["group_by"] = None
    data["limit"] = None

    if dimension == "period":
        data["year"] = item.year
        data["month"] = item.month
        data["start_date"] = item.start_date
        data["end_date"] = item.end_date

    elif dimension in {"praca", "store_name", "location_term"}:
        # Essas dimensões são mutuamente exclusivas no estado comum.
        data["praca"] = None
        data["store_name"] = None
        data["location_term"] = None
        data[dimension] = item.value

    elif dimension == "status":
        data["status"] = None
        data["statuses"] = [item.value]
        data["event"] = "current_status"

    else:
        data[dimension] = item.value

    state = StructuredQueryState.model_validate(data)
    _validate_state("count", state)
    return state


def _count_for_state(db: Session, state: StructuredQueryState) -> int:
    predicates = _build_predicates(state)
    statement = select(func.count().label("total")).select_from(Service)

    if predicates:
        statement = statement.where(and_(*predicates))

    value = db.execute(statement).scalar_one()
    return int(value or 0)


def _normalize_group_label(value: Any) -> str:
    if value is None:
        return "Não informado"
    text = str(value).strip()
    return text or "Não informado"


def _group_counts_for_state(
    db: Session,
    state: StructuredQueryState,
    group_by: str,
) -> dict[str, int]:
    column = GROUP_FIELDS[group_by]
    predicates = _build_predicates(state)
    statement = (
        select(column.label("group_value"), func.count().label("total"))
        .select_from(Service)
        .group_by(column)
    )

    if predicates:
        statement = statement.where(and_(*predicates))

    totals: dict[str, int] = {}
    for row in db.execute(statement).mappings().all():
        label = _normalize_group_label(row["group_value"])
        totals[label] = totals.get(label, 0) + int(row["total"] or 0)

    return totals


def _direction_for_difference(difference: int) -> str:
    if difference > 0:
        return "increase"
    if difference < 0:
        return "decrease"
    return "stable"


def _percentage_change(base_total: int, target_total: int) -> float | None:
    difference = target_total - base_total
    if base_total == 0:
        return 0.0 if target_total == 0 else None
    return round((difference / base_total) * 100, 2)


def _comparison_breakdown(
    db: Session,
    request: StructuredQueryRequest,
) -> list[dict[str, Any]] | None:
    comparison = request.comparison
    if comparison is None or comparison.breakdown_by is None:
        return None

    base_state = _state_for_comparison_item(
        request.state, comparison.dimension, comparison.items[0]
    )
    target_state = _state_for_comparison_item(
        request.state, comparison.dimension, comparison.items[1]
    )

    base_counts = _group_counts_for_state(db, base_state, comparison.breakdown_by)
    target_counts = _group_counts_for_state(db, target_state, comparison.breakdown_by)

    rows: list[dict[str, Any]] = []
    for label in sorted(set(base_counts) | set(target_counts)):
        base_total = base_counts.get(label, 0)
        target_total = target_counts.get(label, 0)
        difference = target_total - base_total
        rows.append(
            {
                "label": label,
                "base_total": base_total,
                "target_total": target_total,
                "difference": difference,
                "percentage_change": _percentage_change(base_total, target_total),
                "direction": _direction_for_difference(difference),
            }
        )

    order = comparison.breakdown_order or "absolute_change"
    if order == "decrease":
        rows = [row for row in rows if row["difference"] < 0]
        rows.sort(key=lambda row: (row["difference"], row["label"].lower()))
    elif order == "increase":
        rows = [row for row in rows if row["difference"] > 0]
        rows.sort(key=lambda row: (-row["difference"], row["label"].lower()))
    else:
        rows.sort(
            key=lambda row: (
                -abs(row["difference"]),
                row["label"].lower(),
            )
        )

    if comparison.breakdown_limit is not None:
        rows = rows[: comparison.breakdown_limit]

    return rows


def _driver_dimensions_for_comparison(comparison: ComparisonSpec) -> list[str]:
    requested = list(comparison.driver_dimensions or DEFAULT_DRIVER_DIMENSIONS)
    dimensions = [
        dimension
        for dimension in requested
        if dimension in BREAKDOWN_DIMENSIONS and dimension != comparison.dimension
    ]

    if dimensions:
        return list(dict.fromkeys(dimensions))

    # Fallback seguro caso a dimensão comparada também seja uma das dimensões padrão.
    for candidate in ("category", "store_name", "praca", "analyst_responsible", "supplier"):
        if candidate != comparison.dimension:
            return [candidate]

    return []


def _driver_contribution_pct(difference: int, net_difference: int) -> float | None:
    if net_difference == 0:
        return None
    return round((difference / net_difference) * 100, 2)


def _comparison_driver_analysis(
    db: Session,
    request: StructuredQueryRequest,
    net_difference: int,
    direction: str,
) -> dict[str, Any] | None:
    comparison = request.comparison
    if comparison is None or comparison.analysis_mode != "drivers":
        return None

    base_state = _state_for_comparison_item(
        request.state, comparison.dimension, comparison.items[0]
    )
    target_state = _state_for_comparison_item(
        request.state, comparison.dimension, comparison.items[1]
    )

    dimensions = _driver_dimensions_for_comparison(comparison)
    limit = comparison.driver_limit or DEFAULT_DRIVER_LIMIT
    dimension_results: list[dict[str, Any]] = []

    for dimension in dimensions:
        base_counts = _group_counts_for_state(db, base_state, dimension)
        target_counts = _group_counts_for_state(db, target_state, dimension)

        changes: list[dict[str, Any]] = []
        for label in sorted(set(base_counts) | set(target_counts)):
            base_total = base_counts.get(label, 0)
            target_total = target_counts.get(label, 0)
            difference = target_total - base_total
            if difference == 0:
                continue

            changes.append(
                {
                    "label": label,
                    "base_total": base_total,
                    "target_total": target_total,
                    "difference": difference,
                    "percentage_change": _percentage_change(base_total, target_total),
                    "direction": _direction_for_difference(difference),
                    # A soma dessa métrica em todos os grupos da dimensão é 100%
                    # quando a variação líquida é diferente de zero. Movimentos
                    # contrários ao saldo possuem contribuição negativa.
                    "contribution_pct": _driver_contribution_pct(
                        difference, net_difference
                    ),
                }
            )

        if direction == "decrease":
            aligned = [row for row in changes if row["difference"] < 0]
            offsets = [row for row in changes if row["difference"] > 0]
            aligned.sort(key=lambda row: (row["difference"], row["label"].lower()))
            offsets.sort(key=lambda row: (-row["difference"], row["label"].lower()))
        elif direction == "increase":
            aligned = [row for row in changes if row["difference"] > 0]
            offsets = [row for row in changes if row["difference"] < 0]
            aligned.sort(key=lambda row: (-row["difference"], row["label"].lower()))
            offsets.sort(key=lambda row: (row["difference"], row["label"].lower()))
        else:
            # Quando o total ficou estável, mostramos os maiores movimentos
            # internos, pois aumentos e reduções se compensaram.
            aligned = sorted(
                changes,
                key=lambda row: (-abs(row["difference"]), row["label"].lower()),
            )
            offsets = []

        if direction == "decrease":
            gross_driver_change = sum(abs(row["difference"]) for row in aligned)
            gross_offset_change = sum(abs(row["difference"]) for row in offsets)
        elif direction == "increase":
            gross_driver_change = sum(abs(row["difference"]) for row in aligned)
            gross_offset_change = sum(abs(row["difference"]) for row in offsets)
        else:
            gross_driver_change = sum(
                row["difference"] for row in changes if row["difference"] > 0
            )
            gross_offset_change = sum(
                abs(row["difference"]) for row in changes if row["difference"] < 0
            )

        dimension_results.append(
            {
                "dimension": dimension,
                "gross_driver_change": gross_driver_change,
                "gross_offset_change": gross_offset_change,
                "top_drivers": aligned[:limit],
                "offsets": offsets[:limit],
            }
        )

    return {
        "mode": "drivers",
        "net_difference": net_difference,
        "direction": direction,
        "dimensions": dimension_results,
    }


def _selection_scope_predicate(context: SelectionContextSpec) -> Any | None:
    comparison = context.source_comparison
    dimension = comparison.dimension
    items = comparison.items

    if dimension == "period":
        date_field = context.source_state.date_field
        if date_field is None:
            raise StructuredQueryError(
                "selection_context herdado de comparação por período exige date_field."
            )

        item_predicates: list[Any] = []
        for item in items:
            scope_state = StructuredQueryState(
                date_field=date_field,
                year=item.year,
                month=item.month,
                start_date=item.start_date,
                end_date=item.end_date,
            )
            predicates = _date_predicates(scope_state)
            if predicates:
                item_predicates.append(and_(*predicates))

        return or_(*item_predicates) if item_predicates else None

    values = [
        item.value.strip()
        for item in items
        if item.value is not None and item.value.strip()
    ]

    if not values:
        return None

    if dimension == "status":
        return Service.status.in_(values)

    if dimension == "location_term":
        return _location_values_predicate(values)

    column = TEXT_FIELDS.get(dimension)
    if column is None:
        return None

    return _text_values_predicate(column, values)


def _comparison_for_selection(context: SelectionContextSpec) -> ComparisonSpec:
    source = context.source_comparison.model_dump()
    limit = context.limit

    if context.mode in {"top_drivers", "offsets"}:
        if context.dimension == context.source_comparison.dimension:
            raise StructuredQueryError(
                "selection_context de drivers não pode repetir a dimensão comparada."
            )

        source.update(
            {
                "breakdown_by": None,
                "breakdown_order": None,
                "breakdown_limit": None,
                "analysis_mode": "drivers",
                "driver_dimensions": [context.dimension],
                "driver_limit": limit or context.source_comparison.driver_limit or DEFAULT_DRIVER_LIMIT,
            }
        )

    elif context.mode == "breakdown":
        if context.dimension == context.source_comparison.dimension:
            raise StructuredQueryError(
                "selection_context de breakdown não pode repetir a dimensão comparada."
            )

        source.update(
            {
                "breakdown_by": context.dimension,
                "breakdown_order": context.source_comparison.breakdown_order
                or "absolute_change",
                "breakdown_limit": limit
                or context.source_comparison.breakdown_limit
                or DEFAULT_DRIVER_LIMIT,
                "analysis_mode": None,
                "driver_dimensions": None,
                "driver_limit": None,
            }
        )

    return ComparisonSpec.model_validate(source)


def _resolve_selection_values(
    db: Session,
    context: SelectionContextSpec,
) -> list[str]:
    if context.mode == "comparison_items":
        if context.dimension != context.source_comparison.dimension:
            raise StructuredQueryError(
                "selection_context comparison_items exige a mesma dimensão da comparação anterior."
            )
        if context.dimension == "period":
            raise StructuredQueryError(
                "comparison_items não pode ser usado como filtro textual para períodos."
            )

        values = [
            item.value.strip()
            for item in context.source_comparison.items
            if item.value is not None and item.value.strip()
        ]
        return list(dict.fromkeys(values))[: context.limit or 100]

    comparison = _comparison_for_selection(context)
    source_request = StructuredQueryRequest(
        query_shape="comparison",
        state=context.source_state,
        comparison=comparison,
    )
    result = _execute_comparison(db, source_request)

    if context.mode in {"top_drivers", "offsets"}:
        analysis = result.get("driver_analysis") or {}
        dimensions = analysis.get("dimensions") or []
        dimension_result = next(
            (
                item
                for item in dimensions
                if item.get("dimension") == context.dimension
            ),
            None,
        )
        if dimension_result is None:
            return []

        key = "top_drivers" if context.mode == "top_drivers" else "offsets"
        rows = dimension_result.get(key) or []
        values = [str(row.get("label", "")).strip() for row in rows]
        return [value for value in values if value]

    breakdown = result.get("breakdown") or []
    values = [str(row.get("label", "")).strip() for row in breakdown]
    return [value for value in values if value]


def _state_with_selection_values(
    state: StructuredQueryState,
    dimension: str,
    values: list[str],
) -> StructuredQueryState:
    data = state.model_dump()

    if dimension == "status":
        data["status"] = None
        data["statuses"] = values or None
        if values:
            data["event"] = "current_status"
        return StructuredQueryState.model_validate(data)

    multi_filters = dict(data.get("multi_filters") or {})
    multi_filters[dimension] = values or ["__SEM_RESULTADO_CONTEXTUAL__"]
    data["multi_filters"] = multi_filters

    # O filtro múltiplo substitui apenas o singular da mesma dimensão.
    # Outros filtros permanecem ativos e podem restringir o conjunto.
    if dimension in data:
        data[dimension] = None

    return StructuredQueryState.model_validate(data)


def _resolve_selection_context(
    db: Session,
    state: StructuredQueryState,
    context: SelectionContextSpec | None,
) -> tuple[StructuredQueryState, Any | None, dict[str, Any] | None]:
    if context is None:
        return state, None, None

    values = _resolve_selection_values(db, context)
    effective_state = _state_with_selection_values(state, context.dimension, values)
    scope_predicate = _selection_scope_predicate(context)

    resolved = {
        "source": "previous_comparison",
        "mode": context.mode,
        "dimension": context.dimension,
        "values": values,
        "inherited_comparison_scope": scope_predicate is not None,
    }

    return effective_state, scope_predicate, resolved


def _execute_comparison(
    db: Session,
    request: StructuredQueryRequest,
) -> dict[str, Any]:
    comparison = request.comparison
    if comparison is None:
        raise StructuredQueryError("comparison é obrigatório quando query_shape=comparison.")

    totals: list[tuple[str, int]] = []

    for item in comparison.items:
        item_state = _state_for_comparison_item(
            request.state,
            comparison.dimension,
            item,
        )
        label = _label_for_comparison_item(comparison.dimension, item)
        total = _count_for_state(db, item_state)
        totals.append((label, total))

    base_label, base_total = totals[0]
    target_label, target_total = totals[1]
    difference = target_total - base_total
    direction = _direction_for_difference(difference)
    percentage_change = _percentage_change(base_total, target_total)
    breakdown = _comparison_breakdown(db, request)
    driver_analysis = _comparison_driver_analysis(
        db, request, difference, direction
    )

    rows = [
        {"label": base_label, "total": base_total},
        {"label": target_label, "total": target_total},
    ]

    comparison_result: dict[str, Any] = {
        "dimension": comparison.dimension,
        "base_label": base_label,
        "target_label": target_label,
        "difference": difference,
        "percentage_change": percentage_change,
        "direction": direction,
    }

    if comparison.breakdown_by is not None:
        comparison_result["breakdown_by"] = comparison.breakdown_by
        comparison_result["breakdown_order"] = (
            comparison.breakdown_order or "absolute_change"
        )

    if comparison.analysis_mode == "drivers":
        comparison_result["analysis_mode"] = "drivers"
        comparison_result["driver_dimensions"] = _driver_dimensions_for_comparison(
            comparison
        )
        comparison_result["driver_limit"] = (
            comparison.driver_limit or DEFAULT_DRIVER_LIMIT
        )

    return {
        "success": True,
        "query_shape": "comparison",
        "row_count": len(rows),
        "truncated": False,
        "columns": ["label", "total"],
        "rows": rows,
        "comparison": comparison_result,
        "breakdown": breakdown,
        "driver_analysis": driver_analysis,
    }


def build_structured_query(
    request: StructuredQueryRequest,
    additional_predicate: Any | None = None,
) -> tuple[Select[Any], bool]:
    _validate_state(request.query_shape, request.state)
    _validate_comparison(request.query_shape, request.state, request.comparison)

    if request.query_shape == "comparison":
        raise StructuredQueryError(
            "comparison produz duas consultas e deve ser executado por execute_structured_query."
        )

    state = request.state
    predicates = _build_predicates(state)
    if additional_predicate is not None:
        predicates.append(additional_predicate)
    where_clause = and_(*predicates) if predicates else None

    if request.query_shape == "count":
        statement = select(func.count().label("total")).select_from(Service)
    elif request.query_shape == "list":
        statement = select(*LIST_FIELDS).order_by(asc(Service.ticket))
    else:
        group_column = GROUP_FIELDS[state.group_by]
        statement = select(group_column.label(state.group_by), func.count().label("total"))
        statement = statement.group_by(group_column).order_by(desc("total"), asc(group_column))

    if where_clause is not None:
        statement = statement.where(where_clause)

    if request.query_shape == "list":
        statement = statement.limit(MAX_LIST_ROWS + 1)
    elif request.query_shape == "ranking":
        statement = statement.limit(state.limit)
    elif request.query_shape == "group" and state.limit is not None:
        statement = statement.limit(state.limit)

    return statement, request.query_shape == "list"


def execute_structured_query(
    db: Session,
    request: StructuredQueryRequest,
) -> dict[str, Any]:
    _validate_state(request.query_shape, request.state)
    _validate_comparison(request.query_shape, request.state, request.comparison)

    effective_state, scope_predicate, resolved_selection = _resolve_selection_context(
        db, request.state, request.selection_context
    )
    effective_request = request.model_copy(
        update={
            "state": effective_state,
            "selection_context": None,
        }
    )

    _validate_state(effective_request.query_shape, effective_request.state)
    _validate_comparison(
        effective_request.query_shape,
        effective_request.state,
        effective_request.comparison,
    )

    if effective_request.query_shape == "comparison":
        response = _execute_comparison(db, effective_request)
        response["resolved_selection"] = resolved_selection
        return response

    statement, is_list = build_structured_query(
        effective_request,
        additional_predicate=scope_predicate,
    )
    result = db.execute(statement)
    columns = list(result.keys())
    raw_rows = [dict(row) for row in result.mappings().all()]
    truncated = is_list and len(raw_rows) > MAX_LIST_ROWS
    rows = raw_rows[:MAX_LIST_ROWS] if truncated else raw_rows

    return {
        "success": True,
        "query_shape": effective_request.query_shape,
        "row_count": len(rows),
        "truncated": truncated,
        "columns": columns,
        "rows": rows,
        "comparison": None,
        "breakdown": None,
        "driver_analysis": None,
        "resolved_selection": resolved_selection,
    }
