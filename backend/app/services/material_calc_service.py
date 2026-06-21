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
M_PRIMER        = "Грунтовка"
M_PUTTY         = "Шпаклевка"
M_LAMINATE      = "Ламинат"
M_LINOLEUM      = "Линолеум"
M_PLINTH        = "Плинтус"
M_TILE          = "Плитка"
M_ADHESIVE      = "Плиточный клей"
M_GROUT         = "Затирка"
M_WALLPAPER     = "Обои"

# Сколько слоёв класть у материалов с unit='л' (для остальных не используется)
LAYERS = {
    M_PAINT_WALLS:   2,
    M_PAINT_CEILING: 2,
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
    Разворачивает repair_options ({floor, walls, ceiling, tile, ...}) в список
    позиций (material_name, area).
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
        sel.append((M_PLINTH, floor_area))
    elif floor == "linoleum":
        sel.append((M_LINOLEUM, floor_area))
        sel.append((M_PLINTH, floor_area))
    elif floor == "parquet":
        # нет материала "Паркет" – только плинтус
        sel.append((M_PLINTH, floor_area))
    # floor == "tile" обрабатывается в блоке плитки

    # --- стены ---
    if walls == "paint":
        sel.append((M_PRIMER, wall_area))
        sel.append((M_PUTTY, wall_area))
        sel.append((M_PAINT_WALLS, wall_area))
    elif walls == "wallpaper":
        sel.append((M_WALLPAPER, wall_area))
    elif walls == "moisture_paint":
        # fallback на обычную краску
        sel.append((M_PAINT_WALLS, wall_area))

    # --- потолок ---
    if ceiling in ("paint", "moisture_paint"):
        sel.append((M_PAINT_CEILING, ceiling_area))
    # stretch – пропускаем

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

def quantity_of(material: Material, area: Decimal, geom: Dict[str, Any]) -> Decimal:
    """Количество в базовых единицах по формуле из estimation-rules.md (по unit)."""
    unit = material.unit
    c = D(material.consumption_per_m2)
    w = D(material.waste_factor) or Decimal(1)

    if unit == "л":
        layers = D(LAYERS.get(material.name, 1))
        return area * layers * c * w
    if unit in ("кг", "м²"):
        return area * (c if c > 0 else Decimal(1)) * w
    if unit == "м":  # плинтус: периметр − ширина дверей
        length = D(geom.get("perimeter")) - D(geom.get("door_width_sum"))
        if length < 0:
            length = Decimal(0)
        return length * w
    if unit == "рулон":  # обои: площадь_стен × (рулонов/м²) × запас
        return area * c * w
    # неизвестная единица — безопасный дефолт
    return area * (c if c > 0 else Decimal(1)) * w


def calculate_materials(
    geometry: Dict[str, Any],
    repair_options: Dict[str, Any],
    db: Session,
) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []

    for material_name, area in _selections(repair_options, geometry):
        material = db.query(Material).filter(Material.name == material_name).first()
        if material is None:
            continue

        quantity = quantity_of(material, area, geometry)

        if quantity <= 0:
            continue

        package_size = D(material.package_size)
        pack_quantity = (quantity / package_size) if package_size > 0 else None

        result.append({
            "material_id": material.id,
            "name": material.name,
            "quantity": quantity,
            "unit": material.unit,
            "package_size": material.package_size,
            "pack_quantity": pack_quantity,
        })

    return result