"""Campos necessários ao painel de manutenção preventiva sincronizados da Tape."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PreventiveService(Base):
    __tablename__ = "preventive_services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    tape_center_record_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("tape_centers.record_id"), nullable=True, index=True,
    )
    praca: Mapped[str | None] = mapped_column(String, nullable=True)
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    subcategory: Mapped[str | None] = mapped_column(String, nullable=True)
    service_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    supplier: Mapped[str | None] = mapped_column(String, nullable=True)
    visit_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    solution_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    analyst_responsible: Mapped[str | None] = mapped_column(String, nullable=True)
    non_approval_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    signature_status: Mapped[str | None] = mapped_column(String, nullable=True)
    signed_pdf_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_on: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completion_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    periodicity: Mapped[str | None] = mapped_column(String, nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sla_status: Mapped[str | None] = mapped_column(String, nullable=True)
    upload_id: Mapped[int] = mapped_column(Integer, ForeignKey("uploads.id"), nullable=False)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
