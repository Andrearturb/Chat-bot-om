from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import Select, and_, asc, desc, func, or_, select
from sqlalchemy.orm import Session

from app.models.service import Service
from app.schemas.structured_query import (
    QUERY_SHAPES,
    StructuredQueryRequest,
    StructuredQueryState,
)

MAX_LIST_ROWS = 200
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


class StructuredQueryError(ValueError):
    pass


def _exact_text(column: Any, value: str) -> Any:
    return func.lower(func.trim(column)) == func.lower(func.trim(value))


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
            f"query_shape inválido: {query_shape}. Use count, list, group ou ranking."
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
        if _parse_date(state.end_date, "end_date") < _parse_date(state.start_date, "start_date"):
            raise StructuredQueryError("end_date não pode ser anterior a start_date.")

    if state.year is not None and state.month is None and not 1 <= state.year <= 9999:
        raise StructuredQueryError("year deve estar entre 1 e 9999.")

    expected_date_field = EVENT_DATE_FIELDS.get(state.event)
    if expected_date_field and state.date_field != expected_date_field:
        raise StructuredQueryError(
            f"event={state.event} exige date_field={expected_date_field}."
        )


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
        end = _next_month(state.year, state.month) if state.month else date(state.year + 1, 1, 1)
        predicates.extend((column >= start, column < end))

    if state.start_date is not None:
        predicates.append(column >= _parse_date(state.start_date, "start_date"))

    if state.end_date is not None:
        end_inclusive = _parse_date(state.end_date, "end_date")
        predicates.append(column < end_inclusive + timedelta(days=1))

    return predicates


def _build_predicates(state: StructuredQueryState) -> list[Any]:
    predicates = _date_predicates(state)

    for field_name, value in TEXT_FIELDS.items():
        field_value = getattr(state, field_name)
        if field_value is not None:
            predicates.append(_exact_text(value, field_value))

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

    if state.missing_field is not None:
        column = TEXT_FIELDS[state.missing_field]
        predicates.append(or_(column.is_(None), func.trim(column) == ""))

    return predicates


def build_structured_query(
    request: StructuredQueryRequest,
) -> tuple[Select[Any], bool]:
    _validate_state(request.query_shape, request.state)
    state = request.state
    predicates = _build_predicates(state)
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
    statement, is_list = build_structured_query(request)
    result = db.execute(statement)
    columns = list(result.keys())
    raw_rows = [dict(row) for row in result.mappings().all()]
    truncated = is_list and len(raw_rows) > MAX_LIST_ROWS
    rows = raw_rows[:MAX_LIST_ROWS] if truncated else raw_rows

    return {
        "success": True,
        "query_shape": request.query_shape,
        "row_count": len(rows),
        "truncated": truncated,
        "columns": columns,
        "rows": rows,
    }
