# app/services/material_calc_service.py

from decimal import Decimal, ROUND_CEILING
from typing import List, Dict, Any, Set
from sqlalchemy.orm import Session
from app.db.models import Material


# ---------------------------------------------------------------------------
# Вспомогательные утилиты
# ---------------------------------------------------------------------------

def D(value) -> Decimal:
    """
    Безопасное приведение к Decimal.

    Геометрия и поля БД могут прийти как float (площадь считается через shoelace,
    колонки могут быть Float). Умножение Decimal * float кидает TypeError,
    поэтому всё, что участвует в арифметике, прогоняем через D().

    Важно: Decimal(str(x)), а не Decimal(x) — иначе притащим float-погрешность
    вида 0.15000000000002.
    """
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal(0)
    return Decimal(str(value))


def packs_to_buy(pack_quantity: Decimal) -> int:
    """
    Перевод дробного количества упаковок в целое число «к покупке» (округление вверх).

    ВНИМАНИЕ: здесь, в расчёте на комнату, мы НЕ округляем. Этот хелпер
    вызывается на этапе агрегации по квартире (B1-5), после суммирования
    одинаковых материалов по всем комнатам. Иначе получим переоценку:
    1.3 + 1.3 → должно быть ceil(2.6)=3, а не ceil(1.3)+ceil(1.3)=4.
    """
    return int(pack_quantity.to_integral_value(rounding=ROUND_CEILING))


def expand_work_types(work_types: List[str]) -> List[str]:
    """
    Разворачивает зависимые материалы.

    Клей и затирка — не «работы», которые выбирает пользователь, а производные
    от плитки. Чтобы не зависеть от фронта, добавляем их здесь, в одном месте.
    Если плитка где-то выбрана — нужен клей и затирка.
    """
    works = list(work_types)
    has_tile = ('tile_floor' in works) or ('tile_wall' in works)
    if has_tile:
        if 'tile_adhesive' not in works:
            works.append('tile_adhesive')
        if 'grout' not in works:
            works.append('grout')
    return works


# ---------------------------------------------------------------------------
# Основной расчёт
# ---------------------------------------------------------------------------

def calculate_materials(
    geometry: Dict[str, Any],
    work_types: List[str],
    db: Session
) -> List[Dict[str, Any]]:
    """
    Рассчитывает количество материалов для выбранных видов работ на основе геометрии.

    Параметры:
        geometry: словарь с размерами комнаты (значения могут быть float или Decimal):
            - wall_area:      площадь стен (м²)
            - floor_area:     площадь пола (м²)
            - ceiling_area:   площадь потолка (м²)
            - perimeter:      периметр пола (м)
            - door_width_sum: суммарная ширина дверных проёмов (м)
        work_types: список идентификаторов работ ('paint_walls', 'laminate_floor', ...)
        db: сессия SQLAlchemy

    Возвращает:
        Список позиций материала. ВАЖНО: quantity и pack_quantity — дробные (Decimal),
        округление до целых упаковок делается на этапе агрегации (B1-5), не здесь.
            - material_id:   id материала из БД (ключ группировки в B1-5!)
            - material_name: название
            - quantity:      кол-во в базовой единице (л / кг / м² / м) — Decimal
            - unit:          единица базового количества
            - pack_quantity: кол-во упаковок (Decimal, дробное) или None
            - pack_unit:     единица упаковки ('банка', 'рулон', 'мешок', ...)
    """
    result: List[Dict[str, Any]] = []
    works: List[str] = expand_work_types(work_types)
    works_set: Set[str] = set(works)

    # -------------------- Нормы расхода по видам работ --------------------
    # Нормы, слои, размеры/коэффициенты запаса берутся из модели Material.
    # Коэффициент запаса в идеале хранить per-material (material.reserve),
    # но если поля нет — используем разумные дефолты ниже.

    def reserve(material: Material, default: str) -> Decimal:
        return D(getattr(material, 'reserve', None) or Decimal(default))

    # 1. Краска для стен
    def calc_paint_walls(material, geom):
        return (D(geom.get('wall_area')) * D(material.layers or 1)
                * D(material.rate) * reserve(material, '1.1'))

    # 2. Грунтовка для стен
    def calc_prime_walls(material, geom):
        return D(geom.get('wall_area')) * D(material.rate) * reserve(material, '1.1')

    # 3. Шпаклёвка для стен
    def calc_putty_walls(material, geom):
        return D(geom.get('wall_area')) * D(material.rate) * reserve(material, '1.1')

    # 4. Краска для потолка
    def calc_paint_ceiling(material, geom):
        return (D(geom.get('ceiling_area')) * D(material.layers or 1)
                * D(material.rate) * reserve(material, '1.1'))

    # 5. Ламинат
    def calc_laminate_floor(material, geom):
        return D(geom.get('floor_area')) * reserve(material, '1.08')

    # 5b. Линолеум (как ламинат, чуть меньше подрезка)
    def calc_linoleum_floor(material, geom):
        return D(geom.get('floor_area')) * reserve(material, '1.05')

    # 6. Плинтус — погонные метры; перевод в хлысты делает pack_size (длина хлыста)
    def calc_skirting(material, geom):
        length = D(geom.get('perimeter')) - D(geom.get('door_width_sum'))
        if length < 0:
            length = Decimal(0)
        return length * reserve(material, '1.07')  # запас на углы под 45°

    # Площадь под плитку: пол + стена, если выбраны обе зоны
    def tiled_area(geom) -> Decimal:
        area = Decimal(0)
        if 'tile_floor' in works_set:
            area += D(geom.get('floor_area'))
        if 'tile_wall' in works_set:
            area += D(geom.get('wall_area'))
        return area

    # 7. Плитка для пола
    def calc_tile_floor(material, geom):
        return D(geom.get('floor_area')) * reserve(material, '1.1')

    # 8. Плитка для стен
    def calc_tile_wall(material, geom):
        return D(geom.get('wall_area')) * reserve(material, '1.1')

    # 9. Клей плиточный — под всю плитку (пол + стена)
    def calc_tile_adhesive(material, geom):
        return tiled_area(geom) * D(material.rate) * reserve(material, '1.1')

    # 9b. Затирка — упрощённо по площади плитки (точнее — по длине швов, но для MVP ок)
    def calc_grout(material, geom):
        return tiled_area(geom) * D(material.rate) * reserve(material, '1.1')

    # 10. Обои — делим на ПОЛЕЗНУЮ площадь рулона (меньше полной из-за подгонки рисунка)
    def calc_wallpaper(material, geom):
        useful = getattr(material, 'roll_useful_area', None)
        if useful:
            coverage = D(useful)
        else:
            # запас на раппорт: ~10% полной площади рулона уходит в подрезку
            coverage = D(material.roll_width) * D(material.roll_length) * Decimal('0.9')
        if coverage == 0:
            return Decimal(0)
        return (D(geom.get('wall_area')) / coverage) * reserve(material, '1.1')

    calc_map = {
        'paint_walls': calc_paint_walls,
        'prime_walls': calc_prime_walls,
        'putty_walls': calc_putty_walls,
        'paint_ceiling': calc_paint_ceiling,
        'laminate_floor': calc_laminate_floor,
        'linoleum_floor': calc_linoleum_floor,
        'skirting': calc_skirting,
        'tile_floor': calc_tile_floor,
        'tile_wall': calc_tile_wall,
        'tile_adhesive': calc_tile_adhesive,
        'grout': calc_grout,
        'wallpaper': calc_wallpaper,
    }

    # -------------------- Основной цикл --------------------
    for work in works:
        if work not in calc_map:
            continue

        material = db.query(Material).filter(Material.service_key == work).first()
        if not material:
            # материал под работу не найден — пропускаем (или логируем)
            continue

        quantity = calc_map[work](material, geometry)
        if quantity <= 0:
            continue

        pack_size = D(material.pack_size)
        pack_quantity = (quantity / pack_size) if pack_size > 0 else None

        result.append({
            'material_id': material.id,        # ← ключ группировки для B1-5
            'material_name': material.name,
            'quantity': quantity,              # дробное, Decimal
            'unit': material.unit,
            'pack_quantity': pack_quantity,    # дробное, округление в агрегации
            'pack_unit': material.pack_unit,
        })

    return result
