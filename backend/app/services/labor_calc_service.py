# app/services/labor_calc_service.py
#
# Расчёт объёма и стоимости работ (B1-2).
# Соответствует реальной схеме БД (app/db/models.py) и контракту api.md.
#
# Модель LaborService: name, specialist, unit
# Модель LaborPrice: price_min, price_avg, price_max, source_id
#
# Поиск услуги — по имени (как в seed_data/labor_services.json).
# Расценки берутся из БД (пока напрямую, позже через агрегатор цен).
# Возвращаются три стоимости (min/avg/max) для каждой работы.

from decimal import Decimal
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.db.models import LaborService, LaborPrice, PriceSource


def calculate_labor(
    geometry: Dict[str, Any],
    repair_options: Dict[str, Any],
    db: Session,
) -> List[Dict[str, Any]]:
    """
    Рассчитывает объём и стоимость работ для одной комнаты.

    Параметры:
        geometry: словарь с геометрией комнаты, содержащий:
            - floor_area: площадь пола (м²)
            - wall_area: площадь стен (м²)
            - ceiling_area: площадь потолка (м²)
            - perimeter: периметр (м) — не используется для работ, но может понадобиться
            - electrical_points: количество электроточек (шт) — опционально
            - plumbing_points: количество сантехточек (шт) — опционально
        repair_options: словарь с выбором отделки (по контракту api.md):
            - floor: "laminate" | "linoleum" | "parquet" | "tile" | None
            - walls: "paint" | "wallpaper" | "moisture_paint" | "tile" | None
            - ceiling: "paint" | "moisture_paint" | "stretch" | None
            - tile: bool (устаревший, но оставлен для совместимости)
            - electric: "basic" | "advanced" | None
            - plumbing: bool
        db: сессия SQLAlchemy

    Возвращает:
        Список словарей, каждый описывает одну работу:
            - service: название услуги (из БД)
            - specialist: специалист (профессия)
            - volume: объём работы (м² или шт)
            - unit: единица измерения (из БД)
            - price_min: стоимость по минимальной расценке
            - price_avg: стоимость по средней расценке
            - price_max: стоимость по максимальной расценке
            - source: источник цены (название)
    """
    result: List[Dict[str, Any]] = []

    # ---- Вспомогательные функции для определения объёма ----

    def volume_painter() -> Decimal:
        """Маляр: площадь стен (если стены красятся) + площадь потолка (если потолок красится)."""
        vol = Decimal(0)
        walls = repair_options.get("walls")
        if walls in ("paint", "moisture_paint"):
            vol += D(geometry.get("wall_area", 0))
        ceiling = repair_options.get("ceiling")
        if ceiling in ("paint", "moisture_paint"):
            vol += D(geometry.get("ceiling_area", 0))
        return vol

    def volume_plasterer() -> Decimal:
        """Штукатур: площадь стен, если стены требуют выравнивания (покраска, обои, но не плитка)."""
        walls = repair_options.get("walls")
        if walls in ("paint", "wallpaper", "moisture_paint"):
            return D(geometry.get("wall_area", 0))
        return Decimal(0)

    def volume_floor_layer() -> Decimal:
        """Укладчик ламината/линолеума/паркета: площадь пола, если выбран соответствующий тип покрытия."""
        floor = repair_options.get("floor")
        if floor in ("laminate", "linoleum", "parquet"):
            return D(geometry.get("floor_area", 0))
        return Decimal(0)

    def volume_tiler() -> Decimal:
        """Плиточник: площадь пола (если пол плитка) + площадь стен (если стены плитка)."""
        vol = Decimal(0)
        floor = repair_options.get("floor")
        if floor == "tile":
            vol += D(geometry.get("floor_area", 0))
        walls = repair_options.get("walls")
        if walls == "tile":
            vol += D(geometry.get("wall_area", 0))
        return vol

    def volume_electrician() -> Decimal:
        """Электрик: количество электроточек (если выбрана работа по электрике)."""
        electric = repair_options.get("electric")
        if electric and electric != "basic":  # если не basic и не false, считаем, что работа нужна
            return D(geometry.get("electrical_points", 0))
        return Decimal(0)

    def volume_plumber() -> Decimal:
        """Сантехник: количество сантехточек (если выбрана работа)."""
        plumbing = repair_options.get("plumbing")
        if plumbing:
            return D(geometry.get("plumbing_points", 0))
        return Decimal(0)

    # ---- Сопоставление имени услуги (как в БД) и функции расчёта объёма ----
    # Имена должны совпадать с полем name в таблице labor_services (seed).
    LABOR_MAP = {
        "Маляр": volume_painter,
        "Штукатур": volume_plasterer,
        "Укладчик ламината": volume_floor_layer,
        "Плиточник": volume_tiler,
        "Электрик": volume_electrician,
        "Сантехник": volume_plumber,
    }

    # ---- Основной цикл ----
    for service_name, volume_func in LABOR_MAP.items():
        volume = volume_func()
        if volume <= 0:
            continue

        # Ищем услугу в БД по имени
        service = db.query(LaborService).filter(LaborService.name == service_name).first()
        if not service:
            # Если услуга не засидована, пропускаем (логгирование можно добавить)
            continue

        # Ищем расценку (пока берём первую запись; в будущем — через агрегатор)
        # Для простоты используем seed-цену (source с именем "seed")
        seed_source = db.query(PriceSource).filter(PriceSource.name == "seed").first()
        if not seed_source:
            # Если seed-источник отсутствует — ищем любую запись
            labor_price = db.query(LaborPrice).filter(LaborPrice.labor_service_id == service.id).first()
        else:
            labor_price = db.query(LaborPrice).filter(
                LaborPrice.labor_service_id == service.id,
                LaborPrice.source_id == seed_source.id
            ).first()

        if not labor_price:
            continue  # нет расценок — не добавляем

        price_min = volume * labor_price.price_min
        price_avg = volume * labor_price.price_avg
        price_max = volume * labor_price.price_max

        # Определяем источник (если есть)
        source_name = "seed"
        if labor_price.source_id:
            source = db.query(PriceSource).filter(PriceSource.id == labor_price.source_id).first()
            if source:
                source_name = source.name

        result.append({
            "service": service.name,
            "specialist": service.specialist,
            "volume": volume,
            "unit": service.unit,
            "price_min": price_min,
            "price_avg": price_avg,
            "price_max": price_max,
            "source": source_name,
        })

    return result


# Вспомогательная функция для безопасного приведения к Decimal
def D(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal(0)
    return Decimal(str(value))