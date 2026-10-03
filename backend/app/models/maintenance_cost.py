"""Partidas individuais de manutenção extraídas da FBL3N do SAP."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.dates import utcnow
from app.db.base import Base
from app.models.tape_center import TapeCenter


class MaintenanceCost(Base):
    __tablename__ = "maintenance_costs"
    __table_args__ = (Index("ix_maintenance_costs_account_posting", "conta_razao", "posting_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    upload_id: Mapped[int] = mapped_column(Integer, ForeignKey("uploads.id"), nullable=False)
    conta_razao: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    posting_date: Mapped[date] = mapped_column(Date, nullable=False)
    document_date: Mapped[date | None] = mapped_column(Date)
    document_number: Mapped[str | None] = mapped_column(String(100))
    posting_key: Mapped[str | None] = mapped_column(String(20))
    document_type: Mapped[str | None] = mapped_column(String(20))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    division: Mapped[str | None] = mapped_column(String(100))
    cost_center: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    tape_center_record_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("tape_centers.record_id"), index=True,
    )
    attribution_source: Mapped[str | None] = mapped_column(String(30))
    supplier_name: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    center: Mapped[TapeCenter | None] = relationship(lazy="joined")

    @property
    def store_name(self) -> str | None:
        return (self.center.name or self.center.title) if self.center else None

    @property
    def praca(self) -> str | None:
        return self.center.praca if self.center else None
