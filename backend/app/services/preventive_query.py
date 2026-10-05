"""Consultas determinísticas dos chamados preventivos do app Tape 57532."""

from datetime import date, datetime, time, timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.preventive_service import PreventiveService as P
from app.models.tape_center import TapeCenter as C
from app.schemas.domain_queries import PreventiveQueryRequest


def _like(value: str) -> str:
    return value.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _exact(column, value: str):
    return func.lower(func.trim(column)) == value.strip().lower()


def _query(request: PreventiveQueryRequest):
    base = select(P).outerjoin(C, C.record_id == P.tape_center_record_id)
    filters = []
    for field, column in (
        ("status", P.status), ("periodicity", P.periodicity),
        ("category", P.category), ("subcategory", P.subcategory),
        ("praca", C.praca),
    ):
        value = getattr(request, field)
        if value:
            filters.append(_exact(column, value))
    if request.store_name:
        filters.append(C.name.ilike(f"%{_like(request.store_name)}%", escape="\\"))
    if request.supplier:
        filters.append(P.supplier.ilike(f"%{_like(request.supplier)}%", escape="\\"))
    date_column = getattr(P, request.date_field)
    if request.year:
        filters.append(func.extract("year", date_column) == request.year)
    if request.month:
        filters.append(func.extract("month", date_column) == request.month)
    if request.start_date:
        filters.append(date_column >= datetime.combine(request.start_date, time.min))
    if request.end_date:
        filters.append(date_column < datetime.combine(request.end_date + timedelta(days=1), time.min))
    if request.overdue is True:
        filters.extend((P.due_date < datetime.combine(date.today(), time.min),
                        or_(P.status.is_(None), func.lower(P.status) != "serviço finalizado")))
    if filters:
        base = base.where(and_(*filters))
    return base


GROUPS = {
    "store_name": C.name, "praca": C.praca, "status": P.status,
    "periodicity": P.periodicity, "category": P.category,
    "subcategory": P.subcategory, "supplier": P.supplier,
}


def execute_preventive_query(db: Session, request: PreventiveQueryRequest) -> dict:
    base = _query(request)
    source = base.with_only_columns(P.id).subquery("filtered_preventive")
    total = db.scalar(select(func.count()).select_from(source)) or 0
    if request.query_shape == "count":
        return {"query_shape": "count", "total_count": total, "rows": [{"total": total}], "truncated": False}

    if request.query_shape == "list":
        limit = min(request.limit or 20, 50)
        rows = db.execute(base.with_only_columns(
            P.ticket, P.status, P.created_on, P.completion_date, P.visit_date,
            P.due_date, P.periodicity, P.category, P.subcategory, P.supplier,
            P.service_description, C.name.label("store_name"), C.praca.label("praca"),
            P.signed_pdf_url,
        ).order_by(P.created_on.desc(), P.id.desc()).limit(limit)).mappings().all()
        return {"query_shape": "list", "total_count": total,
                "rows": [dict(row) for row in rows], "truncated": total > len(rows)}

    column = GROUPS[request.group_by]
    grouped = base.with_only_columns(column.label("label"), func.count(P.id).label("total"))
    grouped = grouped.group_by(column)
    group_count = db.scalar(select(func.count()).select_from(grouped.subquery())) or 0
    limit = min(request.limit or (10 if request.query_shape == "ranking" else 100), 100)
    rows = db.execute(grouped.order_by(func.count(P.id).desc(), column).limit(limit)).mappings().all()
    return {"query_shape": request.query_shape, "group_by": request.group_by,
            "total_count": group_count, "rows": [dict(row) for row in rows],
            "truncated": group_count > len(rows)}
