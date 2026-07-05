# app/services/labor_calc_service.py
#
# Расчёт объёма и стоимости работ (B1-2).
# Соответствует реальной схеме БД и контракту docs/api.md.
#
# ВАЖНО про схему: услуги в seed заданы ОПЕРАЦИЯМИ, не профессиями:
#   name = "Покраска стен"/"Укладка ламината"/...  (по нему ищем услугу)
#   specialist_type = "Маляр"/"Укладчик"/...       (это поле, НЕ "specialist")
# Поэтому сопоставляем repair_options -> имя ОПЕРАЦИИ, а не специалиста.
#
# Контракт строки labor[]:
#   service, specialist, volume, unit, price_avg (за единицу), total_avg (= volume*price)
# Здесь отдаём min/avg/max и по цене за единицу, и по итогу — для summary B1-5.

from decimal import Decimal
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.db.models import LaborService, LaborPrice, PriceSource


def D(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal(0)
    return Decimal(str(value))


# ---- имена операций (как в seed_data/labor_services.json) ----
S_PAINT_WALLS   = "Покраска стен"
S_PAINT_CEILING = "Покраска потолка"
S_PUTTY_WALLS   = "Шпаклевка стен"
S_LAY_LAMINATE  = "Укладка ламината"
S_LAY_TILE      = "Укладка плитки"
S_ELECTRIC      = "Электромонтаж"
S_PLUMBING      = "Сантехнические работы"
S_REVEAL        = "Отделка откосов"


def _labor_selections(repair_options: Dict[str, Any], geom: Dict[str, Any]) -> List[tuple]:
    """repair_options -> список (имя_операции, объём)."""
    walls   = repair_options.get("walls")
    ceiling = repair_options.get("ceiling")
    floor   = repair_options.get("floor")

    wall_area    = D(geom.get("wall_area"))
    ceiling_area = D(geom.get("ceiling_area"))
    floor_area   = D(geom.get("floor_area"))

    sel: List[tuple] = []

    # --- стены ---
    if walls in ("paint", "moisture_paint"):
        sel.append((S_PUTTY_WALLS, wall_area))   # подготовка
        sel.append((S_PAINT_WALLS, wall_area))
    elif walls == "wallpaper":
        sel.append((S_PUTTY_WALLS, wall_area))   # подготовка под обои
        # услуги "Поклейка обоев" в seed НЕТ — поклейка как работа не посчитается (см. примечание)

    # --- потолок ---
    if ceiling in ("paint", "moisture_paint"):
        sel.append((S_PAINT_CEILING, ceiling_area))
    # ceiling == "stretch": услуги монтажа натяжного в seed нет → пропуск

    # --- пол ---
    if floor == "laminate":
        sel.append((S_LAY_LAMINATE, floor_area))
    elif floor in ("linoleum", "parquet"):
        sel.append((S_LAY_LAMINATE, floor_area))  # отдельной услуги нет → fallback на укладку

    # --- плитка (пол + стены одной услугой) ---
    tiled = Decimal(0)
    if floor == "tile":
        tiled += floor_area
    if walls == "tile":
        tiled += wall_area
    if tiled > 0:
        sel.append((S_LAY_TILE, tiled))

    # --- электрика (объём в точках; точки приходят из входа комнаты) ---
    if repair_options.get("electric") in ("basic", "extended"):
        pts = D(geom.get("electrical_points"))
        if pts > 0:
            sel.append((S_ELECTRIC, pts))

    # --- сантехника ---
    if repair_options.get("plumbing"):
        pts = D(geom.get("plumbing_points"))
        if pts > 0:
            sel.append((S_PLUMBING, pts))

    reveal_length = D(geom.get('reveal_length', 0))
    if reveal_length > 0:
        sel.append((S_REVEAL, reveal_length))


    return sel


def _seed_source_id(db: Session):
    src = db.query(PriceSource).filter(PriceSource.name == "seed").first()
    return src.id if src else None


def calculate_labor(
    geometry: Dict[str, Any],
    repair_options: Dict[str, Any],
    db: Session,
) -> List[Dict[str, Any]]:
    """
    Объём и стоимость работ для одной комнаты.

    geometry: floor_area, ceiling_area, wall_area (+ electrical_points / plumbing_points,
              если есть электрика/сантехника — их кладёт B1-5 из входа/типа комнаты).
    repair_options: {floor, walls, ceiling, electric, plumbing, ...}

    Возвращает строки по контракту api.md:
        service, specialist, volume, unit,
        price_min/avg/max (за единицу), total_min/avg/max (= volume * price), source
    """
    result: List[Dict[str, Any]] = []
    seed_id = _seed_source_id(db)

    for service_name, volume in _labor_selections(repair_options, geometry):
        if volume <= 0:
            continue

        service = db.query(LaborService).filter(LaborService.name == service_name).first()
        if service is None:
            continue  # услуга не засидована — пропускаем

        q = db.query(LaborPrice).filter(LaborPrice.labor_service_id == service.id)
        price = q.filter(LaborPrice.source_id == seed_id).first() if seed_id else None
        if price is None:
            price = q.first()  # fallback на любой источник
        if price is None:
            continue

        source_name = "seed"
        if price.source_id:
            src = db.query(PriceSource).filter(PriceSource.id == price.source_id).first()
            if src:
                source_name = src.name

        p_min, p_avg, p_max = D(price.price_min), D(price.price_avg), D(price.price_max)

        result.append({
            "service": service.name,                 # операция
            "specialist": service.specialist_type,   # ← поле specialist_type, не specialist
            "volume": volume,
            "unit": service.unit,
            "price_min": p_min,                       # цена за единицу
            "price_avg": p_avg,
            "price_max": p_max,
            "total_min": volume * p_min,              # итог по строке
            "total_avg": volume * p_avg,
            "total_max": volume * p_max,
            "source": source_name,
        })

    return result
