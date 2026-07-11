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
    # Машинный ключ для поиска в расчётных сервисах (#278) — name остаётся
    # человекочитаемым label для API-ответов, по нему ничего не матчится в коде.
    slug: Mapped[str] = mapped_column(unique=True)
    category: Mapped[str]
    unit: Mapped[str]
    package_size: Mapped[float | None]   # nullable - просто через | None
    consumption_per_m2: Mapped[float | None]   # расход на м²
    waste_factor: Mapped[float | None]          # коэффициент запаса (1.1 / 1.08 ...)
    # Число слоёв для материалов с unit='л' (краска/грунт); NULL = 1 слой по
    # умолчанию (см. quantity_of в material_calc_service.py, #278).
    layers: Mapped[int | None]
    # Надбавка на подгонку рисунка (раппорт) — применяется только при
    # repair_options.wallpaper_pattern; NULL = без надбавки (см. #278).
    pattern_factor: Mapped[float | None]


class LaborService(Base):
    __tablename__ = "labor_services"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    # Машинный ключ для поиска в расчётных сервисах (#278) — см. Material.slug.
    slug: Mapped[str] = mapped_column(unique=True)
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
    # Ссылка на карточку/категорию товара у источника. Заполняет парсер;
    # для seed-цен NULL (показать «нет ссылки» / не делать ссылку на фронте).
    source_url: Mapped[str | None]
    # Фасовка КОНКРЕТНОГО товара за source_url (#306) — не справочная
    # Material.package_size, а то, что парсер реально извлёк у этого товара
    # (объём/вес из названия, длина рейки, соотношение блоков цены). NULL для
    # seed/manual и когда парсер не смог её распознать — расчёт откатывается
    # на статичный Material.package_size (см. estimates.py).
    package_size: Mapped[float | None]
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
    # Ссылка на страницу услуги у источника. Заполняет парсер; для seed NULL.
    source_url: Mapped[str | None]
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())


class RoomType(Base):
    __tablename__ = "room_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(unique=True)   # living / kitchen / bathroom / hallway
    label: Mapped[str]
    rules: Mapped[dict] = mapped_column(JSONB)       # весь объект правил типа (floor/walls/.../plumbing)


class Project(Base):
    """Сохранённый план ремонта (#295): комнаты/точки/проёмы/отделки + метаданные.

    Без auth/user (в проекте их нет) — доступ к CRUD по id, публичная read-only
    ссылка-шеринг по отдельному share_token."""
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    city: Mapped[str]
    # План комнат — тот же контракт, что EstimateRequest.rooms (app/schemas/estimate.py:
    # RoomInput), храним как есть без нормализации в отдельные таблицы.
    rooms: Mapped[list] = mapped_column(JSONB)
    scope: Mapped[str] = mapped_column(default="finish_only")
    share_token: Mapped[str] = mapped_column(unique=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
