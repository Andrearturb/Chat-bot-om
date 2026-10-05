"""Consultas determinísticas das partidas SAP; estornos mantêm o sinal."""

from datetime import timedelta
from decimal import Decimal

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models.maintenance_cost import MaintenanceCost as M
from app.models.tape_center import TapeCenter as C
from app.schemas.domain_queries import CostQueryRequest


def _like(value: str) -> str:
    return value.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _query(request: CostQueryRequest):
    base = select(M).outerjoin(C, C.record_id == M.tape_center_record_id)
    filters = []
    if request.conta_razao:
        filters.append(M.conta_razao == request.conta_razao.strip())
    if request.store_name:
        filters.append(C.name.ilike(f"%{_like(request.store_name)}%", escape="\\"))
    if request.praca:
        filters.append(func.lower(func.trim(C.praca)) == request.praca.strip().lower())
    if request.supplier:
        filters.append(M.supplier_name.ilike(f"%{_like(request.supplier)}%", escape="\\"))
    if request.unattributed is True:
        filters.append(M.tape_center_record_id.is_(None))
    if request.year:
        filters.append(func.extract("year", M.posting_date) == request.year)
    if request.month:
        filters.append(func.extract("month", M.posting_date) == request.month)
    if request.start_date:
        filters.append(M.posting_date >= request.start_date)
    if request.end_date:
        filters.append(M.posting_date < request.end_date + timedelta(days=1))
    if filters:
        base = base.where(and_(*filters))
    return base


GROUPS = {
    "store_name": C.name, "praca": C.praca, "supplier": M.supplier_name,
    "conta_razao": M.conta_razao,
    "year": func.extract("year", M.posting_date),
    "month": func.extract("month", M.posting_date),
}


def _money(value) -> str:
    return str(value if value is not None else Decimal("0.00"))


def execute_cost_query(db: Session, request: CostQueryRequest) -> dict:
    if request.unsupported_filter:
        return {"query_shape": request.query_shape, "total_count": 0, "rows": [],
                "truncated": False, "unsupported_filter": request.unsupported_filter}
    base = _query(request)
    totals = db.execute(base.with_only_columns(
        func.count(M.id), func.sum(M.amount),
    )).one()
    count, amount = totals[0] or 0, totals[1]
    if request.query_shape == "count":
        return {"query_shape": "count", "total_count": count,
                "total_amount": _money(amount),
                "rows": [{"total": count, "total_amount": _money(amount)}], "truncated": False}

    if request.query_shape == "list":
        limit = min(request.limit or 20, 50)
        rows = db.execute(base.with_only_columns(
            M.id, M.conta_razao, M.posting_date, M.document_date,
            M.document_number, M.posting_key, M.amount, M.cost_center,
            M.supplier_name.label("supplier"), M.description,
            C.name.label("store_name"), C.praca.label("praca"),
        ).order_by(M.posting_date.desc(), M.id.desc()).limit(limit)).mappings().all()
        return {"query_shape": "list", "total_count": count,
                "total_amount": _money(amount),
                "rows": [{**dict(row), "amount": _money(row["amount"])} for row in rows],
                "truncated": count > len(rows)}

    column = GROUPS[request.group_by]
    grouped = base.with_only_columns(
        column.label("label"), func.count(M.id).label("total"),
        func.sum(M.amount).label("total_amount"),
    ).group_by(column)
    group_count = db.scalar(select(func.count()).select_from(grouped.subquery())) or 0
    limit = min(request.limit or (10 if request.query_shape == "ranking" else 100), 100)
    rows = db.execute(grouped.order_by(func.sum(M.amount).desc(), column).limit(limit)).mappings().all()
    return {"query_shape": request.query_shape, "group_by": request.group_by,
            "total_count": group_count, "total_amount": _money(amount),
            "rows": [{**dict(row), "total_amount": _money(row["total_amount"])} for row in rows],
            "truncated": group_count > len(rows)}
