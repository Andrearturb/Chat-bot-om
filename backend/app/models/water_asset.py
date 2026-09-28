from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WaterAsset(Base):
    __tablename__ = "water_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("asset_stores.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    equipment_type: Mapped[str] = mapped_column(String(50), nullable=False, default="Purificador")
    location: Mapped[str] = mapped_column(String(255), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(150), nullable=True)
    model: Mapped[str | None] = mapped_column(String(150), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(150), nullable=True)
    manufacture_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    installation_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    voltage: Mapped[str | None] = mapped_column(String(50), nullable=True)
    last_filter_change: Mapped[date | None] = mapped_column(Date, nullable=True)
    next_filter_change: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="Operacional")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
