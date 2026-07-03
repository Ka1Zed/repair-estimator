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
# Инженерка (works.electric / works.plumbing) — гранулярные операции по явным числам.
S_CABLE_LAY     = "Прокладка кабеля"
S_SOCKET_MOUNT  = "Монтаж розетки"
S_LIGHT_MOUNT   = "Монтаж светильника"
S_PIPE_MOUNT    = "Монтаж труб"
S_PLUMBING      = "Сантехнические работы"
# Черновые работы (#190) — добавляются только при scope=rough_and_finish.
S_DEMOLITION    = "Демонтаж"
S_LEVEL_WALLS   = "Выравнивание стен"
S_SCREED_FLOOR  = "Стяжка пола"
S_WATERPROOF    = "Гидроизоляция"
S_PRIMER        = "Грунтование"


# ---- стадии ремонта (#190): rough / pre_finish / finish ----
# Источник правды — docs/estimation-rules.md, раздел «Стадии работ и порядок».
# Мапа keyed по имени операции; строка без записи считается finish (чистовая).
STAGE_BY_SERVICE = {
    # черновая: снос, выравнивание, мокрые процессы, грунт, разводка инженерки
    S_DEMOLITION:   "rough",
    S_LEVEL_WALLS:  "rough",
    S_SCREED_FLOOR: "rough",
    S_WATERPROOF:   "rough",
    S_PRIMER:       "rough",
    S_CABLE_LAY:    "rough",   # разводка электрики — черновой этап
    S_PIPE_MOUNT:   "rough",   # разводка сантехники — черновой этап
    # предчистовая: подготовка основания под финиш
    S_PUTTY_WALLS:  "pre_finish",
    # чистовая: финишная отделка и установка приборов
    S_PAINT_WALLS:   "finish",
    S_PAINT_CEILING: "finish",
    S_LAY_LAMINATE:  "finish",
    S_LAY_TILE:      "finish",
    S_SOCKET_MOUNT:  "finish",
    S_LIGHT_MOUNT:   "finish",
    S_PLUMBING:      "finish",
}

# Типы комнат-мокрых зон: гидроизоляция обязательна (docs/estimation-rules.md).
# Значения — id из docs/room-types.json. Появится новый мокрый тип (напр. кухня-
# мойка) — добавить и сюда, и в room-types.json синхронно.
WET_ROOM_TYPES = {"bathroom"}


def stage_of(service_name: str) -> str:
    """Стадия ремонта по имени операции; дефолт — finish (чистовая)."""
    return STAGE_BY_SERVICE.get(service_name, "finish")


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

    # Электрика/сантехника здесь НЕ считаются: они идут по явным числам works
    # через calculate_engineering_labor (#222).
    return sel


def _seed_source_id(db: Session):
    src = db.query(PriceSource).filter(PriceSource.name == "seed").first()
    return src.id if src else None


def _labor_rows(selections: List[tuple], db: Session, seed_id) -> List[Dict[str, Any]]:
    """Собрать строки сметы работ по списку (имя_операции, объём)."""
    result: List[Dict[str, Any]] = []

    for service_name, volume in selections:
        volume = D(volume)
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
            "stage": stage_of(service.name),         # стадия ремонта (#190)
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


def calculate_labor(
    geometry: Dict[str, Any],
    repair_options: Dict[str, Any],
    db: Session,
) -> List[Dict[str, Any]]:
    """
    Объём и стоимость отделочных работ для одной комнаты (пол/стены/потолок).

    Электрика и сантехника считаются отдельно (calculate_engineering_labor) по явным
    числам works, а не по геометрии — см. #222.

    geometry: floor_area, ceiling_area, wall_area
    repair_options: {floor, walls, ceiling, ...}

    Возвращает строки по контракту api.md:
        service, specialist, volume, unit,
        price_min/avg/max (за единицу), total_min/avg/max (= volume * price), source
    """
    return _labor_rows(_labor_selections(repair_options, geometry), db, _seed_source_id(db))


def calculate_rough_labor(
    geometry: Dict[str, Any],
    repair_options: Dict[str, Any],
    room_type: str,
    db: Session,
) -> List[Dict[str, Any]]:
    """Черновые работы одной комнаты (#190), только при scope=rough_and_finish.

    Жёсткие связки (docs/estimation-rules.md, «Стадии работ и порядок»):
      - демонтаж старой отделки — всегда (по площади пола);
      - отделка стен (покраска/обои/плитка) тянет выравнивание стен + грунт;
      - отделка пола тянет стяжку;
      - мокрая зона (санузел) тянет гидроизоляцию; в сухой комнате плитка на полу
        сама по себе гидроизоляцию не требует.

    Материалы черновых стадий пока не считаем — это отдельная строка работ
    (labor-only), материалы черновой — follow-up (см. issue #190).
    """
    walls = repair_options.get("walls")
    floor = repair_options.get("floor")
    wall_area = D(geometry.get("wall_area"))
    floor_area = D(geometry.get("floor_area"))

    sel: List[tuple] = [(S_DEMOLITION, floor_area)]

    if walls is not None:
        sel.append((S_LEVEL_WALLS, wall_area))   # плитка/покраска тянут выравнивание
        sel.append((S_PRIMER, wall_area))        # грунт между черновой и предчистовой
    if floor is not None:
        sel.append((S_SCREED_FLOOR, floor_area))
    if room_type in WET_ROOM_TYPES:
        sel.append((S_WATERPROOF, floor_area))   # гидроизоляция обязательна в мокрой зоне

    return _labor_rows(sel, db, _seed_source_id(db))


def calculate_engineering_labor(
    sockets: Any,
    lights: Any,
    cable_m: Any,
    plumbing_points: Any,
    pipe_m: Any,
    db: Session,
) -> List[Dict[str, Any]]:
    """Работы электрики/сантехники по явным числам из works (#222).

    Маппинг поле → операция (источник правды docs/estimation-rules.md):
        cable_m → Прокладка кабеля, sockets → Монтаж розетки,
        lights → Монтаж светильника, pipe_m → Монтаж труб,
        plumbing.points → Сантехнические работы (подключение приборов).
    """
    selections = [
        (S_CABLE_LAY, cable_m),
        (S_SOCKET_MOUNT, sockets),
        (S_LIGHT_MOUNT, lights),
        (S_PIPE_MOUNT, pipe_m),
        (S_PLUMBING, plumbing_points),
    ]
    return _labor_rows(selections, db, _seed_source_id(db))
