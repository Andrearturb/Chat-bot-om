from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.dates import utcnow
from app.db.base import Base


class FireAsset(Base):
    __tablename__ = "fire_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("asset_stores.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    equipment_type: Mapped[str] = mapped_column(String(100), nullable=False, default="Extintor")
    extinguisher_agent: Mapped[str | None] = mapped_column(String(80), nullable=True)
    capacity: Mapped[str | None] = mapped_column(String(80), nullable=True)
    location: Mapped[str] = mapped_column(String(255), nullable=False)
    manufacture_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expiration_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    hydrostatic_test_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="Operacional")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
