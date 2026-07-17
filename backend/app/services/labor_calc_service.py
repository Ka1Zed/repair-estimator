# app/services/labor_calc_service.py
#
# Расчёт объёма и стоимости работ (B1-2).
# Соответствует реальной схеме БД и контракту docs/api.md.
#
# ВАЖНО про схему: услуги в seed заданы ОПЕРАЦИЯМИ, не профессиями:
#   name = "Покраска стен"/"Укладка ламината"/... (человекочитаемый label для API)
#   slug = "paint_walls"/"lay_laminate"/...        (машинный ключ, по нему ищем услугу)
#   specialist_type = "Маляр"/"Укладчик"/...       (это поле, НЕ "specialist")
# Поэтому сопоставляем repair_options -> slug ОПЕРАЦИИ, а не специалиста.
#
# Контракт строки labor[]:
#   service, specialist, volume, unit, price_avg (за единицу), total_avg (= volume*price)
# Здесь отдаём min/avg/max и по цене за единицу, и по итогу — для summary B1-5.

from decimal import Decimal
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.db.models import LaborService, LaborPrice, PriceSource
from app.services._num import D


# ---- slug операций (как в seed_data/labor_services.json, поле slug) ----
S_PAINT_WALLS   = "paint_walls"
S_PAINT_CEILING = "paint_ceiling"
S_PUTTY_WALLS   = "putty_walls"
S_WALLPAPER     = "wallpaper_gluing"
S_LAY_LAMINATE  = "lay_laminate"
S_LAY_LINOLEUM  = "lay_linoleum"
S_LAY_PARQUET   = "lay_parquet"
S_LAY_TILE      = "lay_tile"
S_STRETCH_CEIL  = "stretch_ceiling"  # полотно, цена за м², материал в цене работы
S_CEIL_EMBED    = "ceiling_embed"    # закладные потолочника под точки света, шт
S_CURTAIN_NICHE = "curtain_niche"    # ниша под гардину/штору в натяжном, пог. м
S_OTKOS         = "otkos"            # откосы проёмов, м², дороже стен (×1.5–2)
S_PUTTY_CEILING = "putty_ceiling"    # подготовка потолка под покраску (#380)
S_PRIMER_CEILING = "priming_ceiling"  # грунт потолка между черновой и предчистовой (#380)
# Инженерка (works.electric / works.plumbing) — гранулярные операции по явным числам.
S_CABLE_LAY     = "cable_lay"
S_SOCKET_MOUNT  = "socket_mount"
S_LIGHT_MOUNT   = "light_mount"
S_PIPE_MOUNT    = "pipe_mount"
S_PLUMBING      = "plumbing_works"
# Черновые работы (#190) — добавляются только при scope=rough_and_finish.
S_DEMOLITION    = "demolition"
S_LEVEL_WALLS   = "level_walls"
S_SCREED_FLOOR  = "screed_floor"
S_WATERPROOF    = "waterproof"
S_PRIMER        = "priming"


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
    S_PRIMER_CEILING: "rough",  # грунт потолка (#380), по аналогии с S_PRIMER стен
    # NB: stage="rough" здесь — только классификация для группировки в UI. В отличие
    # от S_DEMOLITION/S_LEVEL_WALLS/S_SCREED_FLOOR/S_WATERPROOF/S_PRIMER, эти две строки
    # НЕ гейтятся флагом scope — считаются в calculate_engineering_labor всегда, по
    # явным works.electric/works.plumbing (см. docs/estimation-rules.md, «Жёсткие связки»).
    S_CABLE_LAY:    "rough",   # разводка электрики — черновой этап
    S_PIPE_MOUNT:   "rough",   # разводка сантехники — черновой этап
    # предчистовая: подготовка основания под финиш
    S_PUTTY_WALLS:  "pre_finish",
    S_PUTTY_CEILING: "pre_finish",  # подготовка потолка (#380), по аналогии с S_PUTTY_WALLS
    # чистовая: финишная отделка и установка приборов
    S_PAINT_WALLS:   "finish",
    S_PAINT_CEILING: "finish",
    S_WALLPAPER:     "finish",
    S_LAY_LAMINATE:  "finish",
    S_LAY_LINOLEUM:  "finish",
    S_LAY_PARQUET:   "finish",
    S_LAY_TILE:      "finish",
    S_STRETCH_CEIL:  "finish",
    S_CEIL_EMBED:    "finish",
    S_CURTAIN_NICHE: "finish",
    S_OTKOS:         "finish",
    S_SOCKET_MOUNT:  "finish",
    S_LIGHT_MOUNT:   "finish",
    S_PLUMBING:      "finish",
}

# Типы комнат-мокрых зон: гидроизоляция обязательна (docs/estimation-rules.md).
# Значения — id из docs/room-types.json. Появится новый мокрый тип (напр. кухня-
# мойка) — добавить и сюда, и в room-types.json синхронно.
WET_ROOM_TYPES = {"bathroom"}


def stage_of(service_slug: str) -> str:
    """Стадия ремонта по slug операции; дефолт — finish (чистовая)."""
    return STAGE_BY_SERVICE.get(service_slug, "finish")


def _labor_selections(repair_options: Dict[str, Any], geom: Dict[str, Any]) -> List[tuple]:
    """repair_options -> список (slug_операции, объём)."""
    walls   = repair_options.get("walls")
    ceiling = repair_options.get("ceiling")
    floor   = repair_options.get("floor")

    wall_area    = D(geom.get("wall_area"))
    ceiling_area = D(geom.get("ceiling_area"))
    floor_area   = D(geom.get("floor_area"))
    otkos_area   = D(geom.get("otkos_area"))

    sel: List[tuple] = []

    # --- стены ---
    # Покраска — одна операция «Покраска стен» независимо от типа краски
    # (обычная/влагостойкая): работа фиксирована за операцию, отличается материал.
    if walls in ("paint", "moisture_paint"):
        sel.append((S_PUTTY_WALLS, wall_area))   # подготовка
        sel.append((S_PAINT_WALLS, wall_area))
    elif walls == "wallpaper":
        sel.append((S_PUTTY_WALLS, wall_area))   # подготовка под обои
        sel.append((S_WALLPAPER, wall_area))     # поклейка

    # --- откосы проёмов (#191) ---
    # Отделываются вместе со стенами и дороже них; отдельная строка, не в wall_area.
    if walls is not None and otkos_area > 0:
        sel.append((S_OTKOS, otkos_area))

    # --- потолок ---
    # Подготовка (#380), симметрично стенам: покраска тянет шпаклёвку потолка
    # (pre_finish), не гейтится scope — как S_PUTTY_WALLS выше.
    if ceiling in ("paint", "moisture_paint"):
        sel.append((S_PUTTY_CEILING, ceiling_area))
        sel.append((S_PAINT_CEILING, ceiling_area))
    elif ceiling == "stretch":
        # Натяжной потолок — блок потолочника (#191): полотно (м²) + закладные под
        # светильники (точки) + ниша под карниз/штору (пог. м), а не множитель площади.
        sel.append((S_STRETCH_CEIL, ceiling_area))   # полотно, материал в цене
        light_points = D(repair_options.get("ceiling_light_points"))
        if light_points > 0:
            sel.append((S_CEIL_EMBED, light_points))
        curtain_niche_m = D(repair_options.get("ceiling_curtain_niche_m"))
        if curtain_niche_m > 0:
            sel.append((S_CURTAIN_NICHE, curtain_niche_m))

    # --- пол ---
    if floor == "laminate":
        sel.append((S_LAY_LAMINATE, floor_area))
    elif floor == "linoleum":
        sel.append((S_LAY_LINOLEUM, floor_area))
    elif floor == "parquet":
        sel.append((S_LAY_PARQUET, floor_area))

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


def _labor_rows(
    selections: List[tuple], db: Session, seed_id,
    sources_by_id: Dict[int, str] | None = None,
) -> List[Dict[str, Any]]:
    """Собрать строки сметы работ по списку (slug_операции, объём).

    sources_by_id — предзагруженный словарь id->name справочника PriceSource
    (передаёт вызывающий, обычно estimates.py); без него на каждую строку шёл
    отдельный запрос к price_sources (N+1, #278).
    """
    result: List[Dict[str, Any]] = []

    for service_slug, volume in selections:
        volume = D(volume)
        if volume <= 0:
            continue

        service = db.query(LaborService).filter(LaborService.slug == service_slug).first()
        if service is None:
            continue  # услуга не засидована — пропускаем

        q = db.query(LaborPrice).filter(LaborPrice.labor_service_id == service.id)
        price = q.filter(LaborPrice.source_id == seed_id).first() if seed_id else None
        if price is None:
            # fallback на любой источник; сортировка по id — выбор детерминирован
            price = q.order_by(LaborPrice.id).first()
        if price is None:
            continue

        source_name = "seed"
        if price.source_id:
            if sources_by_id is not None:
                source_name = sources_by_id.get(price.source_id, "seed")
            else:
                src = db.query(PriceSource).filter(PriceSource.id == price.source_id).first()
                if src:
                    source_name = src.name

        p_min, p_avg, p_max = D(price.price_min), D(price.price_avg), D(price.price_max)

        result.append({
            "service": service.name,                 # операция (display, не slug)
            "specialist": service.specialist_type,   # ← поле specialist_type, не specialist
            "stage": stage_of(service.slug),         # стадия ремонта (#190)
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
    sources_by_id: Dict[int, str] | None = None,
    include_finish: bool = True,
) -> List[Dict[str, Any]]:
    """
    Объём и стоимость отделочных работ для одной комнаты (пол/стены/потолок).

    Электрика и сантехника считаются отдельно (calculate_engineering_labor) по явным
    числам works, а не по геометрии — см. #222.

    geometry: floor_area, ceiling_area, wall_area
    repair_options: {floor, walls, ceiling, ...}
    sources_by_id: предзагруженный словарь PriceSource id->name (см. _labor_rows).
    include_finish: False при scope=rough_only (#303) — отбрасывает строки stage="finish"
        (покраска/обои/плитка/ламинат/откосы/натяжной потолок), но оставляет "Шпаклевку
        стен" (stage="pre_finish") — она не входит в жёсткие связки scope, см.
        docs/estimation-rules.md.

    Возвращает строки по контракту api.md:
        service, specialist, volume, unit,
        price_min/avg/max (за единицу), total_min/avg/max (= volume * price), source
    """
    selections = _labor_selections(repair_options, geometry)
    if not include_finish:
        selections = [(slug, vol) for slug, vol in selections if stage_of(slug) != "finish"]
    return _labor_rows(selections, db, _seed_source_id(db), sources_by_id=sources_by_id)


def calculate_rough_labor(
    geometry: Dict[str, Any],
    repair_options: Dict[str, Any],
    room_type: str,
    db: Session,
    sources_by_id: Dict[int, str] | None = None,
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
    ceiling = repair_options.get("ceiling")
    floor = repair_options.get("floor")
    wall_area = D(geometry.get("wall_area"))
    ceiling_area = D(geometry.get("ceiling_area"))
    floor_area = D(geometry.get("floor_area"))

    sel: List[tuple] = [(S_DEMOLITION, floor_area)]

    if walls is not None:
        sel.append((S_LEVEL_WALLS, wall_area))   # плитка/покраска тянут выравнивание
        sel.append((S_PRIMER, wall_area))        # грунт между черновой и предчистовой
    # Грунт потолка (#380), симметрично стенам — только под покраску (как и материал
    # M_PRIMER потолка в _selections), не под натяжной (там своя подготовка не нужна).
    if ceiling in ("paint", "moisture_paint"):
        sel.append((S_PRIMER_CEILING, ceiling_area))
    if floor is not None:
        sel.append((S_SCREED_FLOOR, floor_area))
    if room_type in WET_ROOM_TYPES:
        sel.append((S_WATERPROOF, floor_area))   # гидроизоляция обязательна в мокрой зоне

    return _labor_rows(sel, db, _seed_source_id(db), sources_by_id=sources_by_id)


def calculate_engineering_labor(
    sockets: Any,
    lights: Any,
    cable_m: Any,
    plumbing_points: Any,
    pipe_m: Any,
    db: Session,
    sources_by_id: Dict[int, str] | None = None,
    include_finish: bool = True,
) -> List[Dict[str, Any]]:
    """Работы электрики/сантехники по явным числам из works (#222).

    Маппинг поле → операция (источник правды docs/estimation-rules.md):
        cable_m → Прокладка кабеля, sockets → Монтаж розетки,
        lights → Монтаж светильника, pipe_m → Монтаж труб,
        plumbing.points → Сантехнические работы (подключение приборов).

    include_finish: False при scope=rough_only (#303) — оставляет только разводку
        (cable_lay/pipe_mount, stage="rough", не гейтится scope и без этого флага),
        убирает монтаж приборов (socket_mount/light_mount/plumbing_works, stage="finish").
    """
    selections = [
        (S_CABLE_LAY, cable_m),
        (S_SOCKET_MOUNT, sockets),
        (S_LIGHT_MOUNT, lights),
        (S_PIPE_MOUNT, pipe_m),
        (S_PLUMBING, plumbing_points),
    ]
    if not include_finish:
        selections = [(slug, vol) for slug, vol in selections if stage_of(slug) != "finish"]
    return _labor_rows(selections, db, _seed_source_id(db), sources_by_id=sources_by_id)
