"""Lojas do app dCentros (30902), identificadas pelo record_id da Tape."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TapeCenter(Base):
    __tablename__ = "tape_centers"

    record_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    unique_number: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    short_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bcps_number: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    sap_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cost_center: Mapped[str | None] = mapped_column(String(100), nullable=True)
    praca: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str | None] = mapped_column(String(100), nullable=True)
    brand: Mapped[str | None] = mapped_column(String(100), nullable=True)
    business_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    company: Mapped[str | None] = mapped_column(String(100), nullable=True)
    uf: Mapped[str | None] = mapped_column(String(2), nullable=True)
    cnpj: Mapped[str | None] = mapped_column(String(30), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    record_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    upload_id: Mapped[int] = mapped_column(Integer, ForeignKey("uploads.id"), nullable=False)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
