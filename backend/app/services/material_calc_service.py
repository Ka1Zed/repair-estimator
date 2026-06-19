# app/services/material_calc_service.py

from decimal import Decimal
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.db.models import Material


def calculate_materials(
    geometry: Dict[str, Decimal],
    work_types: List[str],
    db: Session
) -> List[Dict[str, Any]]:
    """
    Рассчитывает количество материалов для выбранных видов работ на основе геометрии помещения.

    Параметры:
        geometry: словарь с размерами комнаты, обязательные ключи:
            - wall_area: площадь стен (м²)
            - floor_area: площадь пола (м²)
            - ceiling_area: площадь потолка (м²)
            - perimeter: периметр пола (м)
            - door_width_sum: суммарная ширина дверных проёмов (м)
        work_types: список идентификаторов работ (например, 'paint_walls', 'laminate_floor')
        db: сессия SQLAlchemy для доступа к базе данных

    Возвращает:
        Список словарей, каждый из которых описывает одну позицию материала:
            - material_name: название материала (из БД)
            - quantity: количество в базовой единице (например, литры, кг, м²)
            - unit: единица измерения базового количества
            - pack_quantity: количество упаковок (может быть дробным)
            - pack_unit: единица упаковки (например, 'банка', 'рулон')
    """
    result = []

    # ---------- Вспомогательные функции для расчёта количества по каждому виду работ ----------
    # Все нормы расхода, количество слоёв, размеры упаковок берутся из модели Material в БД.

    # 1. Краска для стен (paint_walls)
    def calc_paint_walls(material: Material, geom: Dict[str, Decimal]) -> Decimal:
        area = geom.get('wall_area', Decimal(0))
        layers = Decimal(material.layers or 1)
        rate = material.rate or Decimal(0)
        return area * layers * rate * Decimal('1.1')

    # 2. Грунтовка для стен (prime_walls)
    def calc_prime_walls(material: Material, geom: Dict[str, Decimal]) -> Decimal:
        area = geom.get('wall_area', Decimal(0))
        rate = material.rate or Decimal(0)
        return area * rate * Decimal('1.1')

    # 3. Шпаклёвка для стен (putty_walls)
    def calc_putty_walls(material: Material, geom: Dict[str, Decimal]) -> Decimal:
        area = geom.get('wall_area', Decimal(0))
        rate = material.rate or Decimal(0)
        return area * rate * Decimal('1.1')

    # 4. Краска для потолка (paint_ceiling)
    def calc_paint_ceiling(material: Material, geom: Dict[str, Decimal]) -> Decimal:
        area = geom.get('ceiling_area', Decimal(0))
        layers = Decimal(material.layers or 1)
        rate = material.rate or Decimal(0)
        return area * layers * rate * Decimal('1.1')

    # 5. Ламинат (laminate_floor)
    def calc_laminate_floor(material: Material, geom: Dict[str, Decimal]) -> Decimal:
        area = geom.get('floor_area', Decimal(0))
        return area * Decimal('1.08')

    # 6. Плинтус (skirting)
    def calc_skirting(material: Material, geom: Dict[str, Decimal]) -> Decimal:
        perimeter = geom.get('perimeter', Decimal(0))
        door_width = geom.get('door_width_sum', Decimal(0))
        length = (perimeter - door_width) * Decimal('1.1')
        # Для плинтуса расход обычно равен 1 (погонный метр на метр)
        rate = material.rate or Decimal(1)
        return length * rate

    # 7. Плитка для пола (tile_floor)
    def calc_tile_floor(material: Material, geom: Dict[str, Decimal]) -> Decimal:
        area = geom.get('floor_area', Decimal(0))
        return area * Decimal('1.1')

    # 8. Плитка для стен (tile_wall)
    def calc_tile_wall(material: Material, geom: Dict[str, Decimal]) -> Decimal:
        area = geom.get('wall_area', Decimal(0))
        return area * Decimal('1.1')

    # 9. Клей плиточный (tile_adhesive)
    def calc_tile_adhesive(material: Material, geom: Dict[str, Decimal]) -> Decimal:
        # Площадь под плитку определяется по тому, какая работа по плитке выбрана
        if 'tile_floor' in work_types:
            area = geom.get('floor_area', Decimal(0))
        elif 'tile_wall' in work_types:
            area = geom.get('wall_area', Decimal(0))
        else:
            area = Decimal(0)
        rate = material.rate or Decimal(0)
        return area * rate * Decimal('1.1')

    # 10. Обои (wallpaper)
    def calc_wallpaper(material: Material, geom: Dict[str, Decimal]) -> Decimal:
        area = geom.get('wall_area', Decimal(0))
        roll_width = material.roll_width or Decimal(0)
        roll_length = material.roll_length or Decimal(0)
        coverage = roll_width * roll_length
        if coverage == 0:
            return Decimal(0)
        return (area / coverage) * Decimal('1.1')

    # Сопоставление идентификатора работы с функцией расчёта
    calc_map = {
        'paint_walls': calc_paint_walls,
        'prime_walls': calc_prime_walls,
        'putty_walls': calc_putty_walls,
        'paint_ceiling': calc_paint_ceiling,
        'laminate_floor': calc_laminate_floor,
        'skirting': calc_skirting,
        'tile_floor': calc_tile_floor,
        'tile_wall': calc_tile_wall,
        'tile_adhesive': calc_tile_adhesive,
        'wallpaper': calc_wallpaper,
    }

    # ---------- Основной цикл по видам работ ----------
    for work in work_types:
        # Ищем материал, соответствующий данной работе (поле service_key в модели Material)
        material = db.query(Material).filter(Material.service_key == work).first()
        if not material:
            # Если материал не найден, пропускаем работу (можно также поднять исключение)
            continue

        if work not in calc_map:
            # Неизвестный тип работы – пропускаем
            continue

        calc_func = calc_map[work]
        quantity = calc_func(material, geometry)
        if quantity <= 0:
            continue

        # Количество упаковок
        pack_size = material.pack_size or Decimal(0)
        if pack_size > 0:
            pack_quantity = quantity / pack_size
        else:
            pack_quantity = None

        result.append({
            'material_name': material.name,   # Название материала из БД
            'quantity': quantity,
            'unit': material.unit,
            'pack_quantity': pack_quantity,
            'pack_unit': material.pack_unit,
        })

    return result