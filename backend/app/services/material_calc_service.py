# app/services/material_calc_service.py
#
# Расчёт количества материалов (B1-1).
# Соответствует реальной схеме БД (app/db/models.py) и контракту docs/estimation-rules.md:
#   - поля материала: name, unit, package_size, consumption_per_m2, waste_factor
#   - материал ищется ПО ИМЕНИ (как в seed)
#   - формула зависит от unit (см. estimation-rules.md)
#   - число слоёв (layers) в БД не хранится — задаётся здесь
#
# Округление до целых упаковок здесь НЕ делается: pack_quantity дробный,
# ceil выполняется на агрегации по квартире (B1-5) после суммирования
# одинаковых материалов — иначе 1.3 + 1.3 даст 4 банки вместо 3.

from decimal import Decimal, ROUND_CEILING
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.db.models import Material


# ---- имена материалов (как в seed_data/materials.json) ----
M_PAINT_WALLS   = "Краска для стен"
M_PAINT_CEILING = "Краска потолочная"
M_PAINT_MOIST   = "Краска влагостойкая"   # влагостойкая (мокрые зоны), стены и потолок
M_PRIMER        = "Грунтовка"
M_PUTTY_START   = "Шпаклевка стартовая"
M_PUTTY         = "Шпаклевка финишная"
M_LAMINATE      = "Ламинат"
M_LINOLEUM      = "Линолеум"
M_PARQUET       = "Паркетная доска"
M_PLINTH        = "Плинтус"
M_TILE          = "Плитка"
M_ADHESIVE      = "Плиточный клей"
M_GROUT         = "Затирка"
M_WALLPAPER     = "Обои"
# Инженерка (works.electric / works.plumbing) — количество берётся из запроса,
# НЕ через quantity_of (там unit «м» захардкожен под плинтус, заметка ревью #230).
M_SOCKET        = "Розетка"
M_LIGHT         = "Светильник"
M_CABLE         = "Кабель электрический"
M_PIPE          = "Труба водопроводная"

# Сколько слоёв класть у материалов с unit='л' (для остальных не используется)
LAYERS = {
    M_PAINT_WALLS:   2,
    M_PAINT_CEILING: 2,
    M_PAINT_MOIST:   2,
    M_PRIMER:        1,
}


def D(value) -> Decimal:
    """Безопасное приведение к Decimal (поля БД — float, геометрия — float)."""
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal(0)
    return Decimal(str(value))


def packs_to_buy(pack_quantity: Decimal) -> int:
    """ceil до целых упаковок. Вызывать на агрегации (B1-5), не на комнате."""
    return int(pack_quantity.to_integral_value(rounding=ROUND_CEILING))


def _selections(repair_options: Dict[str, Any], geom: Dict[str, Any]) -> List[tuple]:
    """
    Разворачивает repair_options ({floor, walls, ceiling, ...}) в список
    позиций (material_name, area) — какую площадь использовать для материала.
    Плинтус и плитка/клей/затирка добавляются как зависимые автоматически.

    area для unit='м' (плинтус) и unit='рулон' (обои) считается внутри
    quantity_of по геометрии, здесь передаётся опорная площадь.
    """
    floor   = repair_options.get("floor")
    walls   = repair_options.get("walls")
    ceiling = repair_options.get("ceiling")

    floor_area   = D(geom.get("floor_area"))
    ceiling_area = D(geom.get("ceiling_area"))
    wall_area    = D(geom.get("wall_area"))

    sel: List[tuple] = []

    # --- пол ---
    if floor == "laminate":
        sel.append((M_LAMINATE, floor_area))
        sel.append((M_PLINTH, floor_area))      # area для плинтуса не важна, считается по периметру
    elif floor == "linoleum":
        sel.append((M_LINOLEUM, floor_area))
        sel.append((M_PLINTH, floor_area))
    elif floor == "parquet":
        sel.append((M_PARQUET, floor_area))
        sel.append((M_PLINTH, floor_area))
    # floor == "tile" обрабатывается в блоке плитки ниже (плинтус не нужен)

    # --- стены ---
    # Покраска (обычная/влагостойкая) идёт с одинаковой подготовкой основания
    # (грунт → стартовая → финишная шпаклёвка), отличается только сама краска.
    if walls in ("paint", "moisture_paint"):
        sel.append((M_PRIMER, wall_area))        # грунтовка, 1 слой
        sel.append((M_PUTTY_START, wall_area))   # стартовая шпаклёвка (выравнивание)
        sel.append((M_PUTTY, wall_area))         # финишная шпаклёвка
        sel.append((M_PAINT_WALLS if walls == "paint" else M_PAINT_MOIST, wall_area))  # 2 слоя
    elif walls == "wallpaper":
        sel.append((M_WALLPAPER, wall_area))

    # --- потолок ---
    if ceiling == "paint":
        sel.append((M_PAINT_CEILING, ceiling_area))
    elif ceiling == "moisture_paint":
        sel.append((M_PAINT_MOIST, ceiling_area))   # влагостойкая (санузел)
    # ceiling == "stretch" (натяжной) — материал (плёнка/профиль) входит в цену
    # работы «Монтаж натяжного потолка» → отдельной строки материала нет

    # --- плитка (пол + стены) ---
    tiled = Decimal(0)
    if floor == "tile":
        tiled += floor_area
    if walls == "tile":
        tiled += wall_area
    if tiled > 0:
        sel.append((M_TILE, tiled))
        sel.append((M_ADHESIVE, tiled))
        sel.append((M_GROUT, tiled))

    return sel


# Надбавка на подгонку рисунка (раппорт) у обоев под рисунок — см. estimation-rules.md.
WALLPAPER_PATTERN_FACTOR = Decimal("1.3")

# Кривизна основания под выравнивание → множитель расхода СТАРТОВОЙ шпаклёвки
# (норма 5.0 кг/м², вилка 3–8, см. estimation-rules.md). Финишную не трогает.
WALL_CONDITION_FACTOR = {
    "even":   Decimal("0.6"),   # ровные стены ≈3 кг/м²
    "normal": Decimal("1.0"),   # дефолт, текущая норма 5.0 кг/м²
    "uneven": Decimal("1.6"),   # кривые ≈8 кг/м²
}


def quantity_of(
    material: Material,
    area: Decimal,
    geom: Dict[str, Any],
    repair_options: Dict[str, Any] | None = None,
) -> tuple[Decimal, Decimal]:
    """Количество в базовых единицах по формуле из estimation-rules.md (по unit).

    Возвращает (quantity, base_quantity): base_quantity — до применения запаса
    (и, для обоев под рисунок, до подгонки по раппорту), quantity = base_quantity × waste_factor
    (у обоев под рисунок в waste_factor дополнительно вшит раппорт — см. #176).
    """
    repair_options = repair_options or {}
    unit = material.unit
    c = D(material.consumption_per_m2)
    w = D(material.waste_factor) or Decimal(1)

    if unit == "л":
        layers = D(LAYERS.get(material.name, 1))
        # Пористое основание → грунт в 2 слоя (см. estimation-rules.md).
        if material.name == M_PRIMER and repair_options.get("primer_two_coats"):
            layers = Decimal(2)
        base = area * layers * c
        return base * w, base
    if unit in ("кг", "м²"):
        base = area * (c if c > 0 else Decimal(1))
        # Кривизна основания масштабирует только стартовую шпаклёвку (выравнивание).
        # Множитель складываем в base (до запаса), как раппорт у обоев.
        if material.name == M_PUTTY_START:
            base = base * WALL_CONDITION_FACTOR.get(
                repair_options.get("wall_condition"), Decimal(1)
            )
        return base * w, base
    if unit == "м":  # плинтус: периметр − ширина дверей
        length = D(geom.get("perimeter")) - D(geom.get("door_width_sum"))
        if length < 0:
            length = Decimal(0)
        return length * w, length
    if unit == "рулон":  # обои: площадь_стен × (рулонов/м²) × запас
        # Обои под рисунок требуют подгонки по раппорту → дополнительный расход ×1.3.
        pattern = WALLPAPER_PATTERN_FACTOR if repair_options.get("wallpaper_pattern") else Decimal(1)
        base = area * c
        return base * w * pattern, base
    # неизвестная единица — безопасный дефолт
    base = area * (c if c > 0 else Decimal(1))
    return base * w, base


def _material_row(
    material: Material, quantity: Decimal, base_quantity: Decimal, waste_factor: Decimal
) -> Dict[str, Any]:
    """Строка материала с готовым (уже посчитанным) количеством в базовых единицах."""
    package_size = D(material.package_size)
    pack_quantity = (quantity / package_size) if package_size > 0 else None
    return {
        "material_id": material.id,
        "name": material.name,
        "quantity": quantity,
        "base_quantity": base_quantity,
        "waste_factor": waste_factor,
        "unit": material.unit,
        "package_size": material.package_size,
        "pack_quantity": pack_quantity,
    }


def calculate_engineering_materials(
    sockets: Any,
    lights: Any,
    cable_m: Any,
    pipe_m: Any,
    db: Session,
) -> List[Dict[str, Any]]:
    """Материалы электрики/сантехники по явным числам из works (не через quantity_of).

    Штучные позиции (розетка, светильник) — количество равно числу из запроса,
    без норм расхода и без запаса. Погонаж (кабель, труба) — метраж × waste_factor;
    труба округляется вверх до хлыста 2 м на общей агрегации (package_size = 2).
    Мелочёвка (подрозетники, фитинги) отдельными строками не заводится — она в стоимости
    работ. См. docs/estimation-rules.md.
    """
    result: List[Dict[str, Any]] = []
    # (имя, количество, применять ли waste_factor) — штучные без запаса, погонаж с запасом.
    specs = [
        (M_SOCKET, sockets, False),
        (M_LIGHT, lights, False),
        (M_CABLE, cable_m, True),
        (M_PIPE, pipe_m, True),
    ]
    for name, count, with_waste in specs:
        qty = D(count)
        if qty <= 0:
            continue
        material = db.query(Material).filter(Material.name == name).first()
        if material is None:
            continue
        base_qty = qty
        waste_factor = Decimal(1)
        if with_waste:
            waste_factor = D(material.waste_factor) or Decimal(1)
            qty = qty * waste_factor
        result.append(_material_row(material, qty, base_qty, waste_factor))
    return result


def calculate_materials(
    geometry: Dict[str, Any],
    repair_options: Dict[str, Any],
    db: Session,
) -> List[Dict[str, Any]]:
    """
    Считает материалы для одной комнаты по геометрии и выбранной отделке.

    geometry: floor_area, ceiling_area, wall_area, perimeter, door_width_sum
    repair_options: {floor, walls, ceiling, electric, plumbing} (контракт api.md)

    Возвращает позиции с ДРОБНЫМ pack_quantity (округление — в B1-5):
        material_id, name, quantity (Decimal), base_quantity, waste_factor,
        unit, package_size, pack_quantity
    """
    result: List[Dict[str, Any]] = []

    for material_name, area in _selections(repair_options, geometry):
        material = db.query(Material).filter(Material.name == material_name).first()
        if material is None:
            # материала нет в БД (например, не засидован) — пропускаем
            continue

        quantity, base_quantity = quantity_of(material, area, geometry, repair_options)
        if quantity <= 0:
            continue

        # Эффективный запас = quantity / base_quantity — тем же числом, каким
        # реально накрутили итог (включает и waste_factor материала, и раппорт
        # обоев, если он применялся), без риска разойтись с quantity (#176).
        waste_factor = (quantity / base_quantity) if base_quantity > 0 else Decimal(1)

        package_size = D(material.package_size)
        pack_quantity = (quantity / package_size) if package_size > 0 else None

        result.append({
            "material_id": material.id,        # ключ группировки в B1-5
            "name": material.name,
            "quantity": quantity,              # дробное, Decimal
            "base_quantity": base_quantity,    # до запаса, дробное
            "waste_factor": waste_factor,      # quantity / base_quantity
            "unit": material.unit,
            "package_size": material.package_size,
            "pack_quantity": pack_quantity,    # дробное; ceil — в агрегации
        })

    return result
