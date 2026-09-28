from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AssetStore(Base):
    __tablename__ = "asset_stores"
    __table_args__ = (UniqueConstraint("store_key", name="uq_asset_stores_store_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    store_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    store_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    bpcs_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sap_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    praca: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
