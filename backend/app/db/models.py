from app.db.session import Base
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import ForeignKey, Numeric, func
from sqlalchemy.dialects.postgresql import JSONB

from datetime import datetime
from decimal import Decimal


class PriceSource(Base):
    __tablename__ = "price_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    type: Mapped[str]
    url: Mapped[str | None]
    last_checked: Mapped[datetime | None]


class Material(Base):
    __tablename__ = "materials"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    category: Mapped[str]
    unit: Mapped[str]
    package_size: Mapped[float | None]   # nullable - просто через | None
    consumption_per_m2: Mapped[float | None]   # расход на м²
    waste_factor: Mapped[float | None]          # коэффициент запаса (1.1 / 1.08 ...)


class LaborService(Base):
    __tablename__ = "labor_services"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    specialist_type: Mapped[str]
    unit: Mapped[str]


class MaterialPrice(Base):
    __tablename__ = "material_prices"

    id: Mapped[int] = mapped_column(primary_key=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"))
    source_id: Mapped[int] = mapped_column(ForeignKey("price_sources.id"))
    price_min: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    price_avg: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    price_max: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    region: Mapped[str | None]
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())


class LaborPrice(Base):
    __tablename__ = "labor_prices"

    id: Mapped[int] = mapped_column(primary_key=True)
    labor_service_id: Mapped[int] = mapped_column(ForeignKey("labor_services.id"))
    source_id: Mapped[int] = mapped_column(ForeignKey("price_sources.id"))
    price_min: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    price_avg: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    price_max: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    region: Mapped[str | None]
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())


class RoomType(Base):
    __tablename__ = "room_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(unique=True)   # living / kitchen / bathroom / hallway
    label: Mapped[str]
    rules: Mapped[dict] = mapped_column(JSONB)       # весь объект правил типа (floor/walls/.../plumbing)