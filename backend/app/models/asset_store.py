"""ID local estável para os ativos, vinculado ao cadastro do dCentros."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.dates import utcnow
from app.db.base import Base
from app.models.tape_center import TapeCenter


class AssetStore(Base):
    __tablename__ = "asset_stores"
    __table_args__ = (UniqueConstraint("tape_center_record_id", name="uq_asset_stores_tape_center_record_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tape_center_record_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("tape_centers.record_id"), nullable=True, index=True,
    )
    center: Mapped[TapeCenter | None] = relationship(lazy="joined")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    @property
    def store_key(self) -> str:
        return f"tape:{self.tape_center_record_id}" if self.tape_center_record_id else f"local:{self.id}"

    @property
    def store_name(self) -> str | None:
        return (self.center.name or self.center.title) if self.center else None

    @property
    def bpcs_number(self) -> str | None:
        return self.center.bcps_number if self.center else None

    @property
    def sap_number(self) -> str | None:
        return self.center.sap_number if self.center else None

    @property
    def praca(self) -> str | None:
        return self.center.praca if self.center else None
