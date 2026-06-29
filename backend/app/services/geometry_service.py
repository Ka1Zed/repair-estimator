
from typing import List, Union, Dict, Any, Optional
from decimal import Decimal, getcontext

getcontext().prec = 28

OPENING_TYPE_RU = {
    'door': 'двери',
    'window': 'окна',
    'unknown': 'проёма'
}

def to_decimal(value: Union[int, float, str, Decimal]) -> Decimal:
    """Преобразует значение в Decimal, избегая ошибок float."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    return Decimal(value)

def _get_xy(p: Union[tuple, list, dict]) -> tuple:
    """Достаёт координаты точки в формате (x, y), [x, y] или {'x': x, 'y': y}."""
    if isinstance(p, dict):
        return to_decimal(p['x']), to_decimal(p['y'])
    return to_decimal(p[0]), to_decimal(p[1])

def side_lengths(points: List[Union[tuple, list, dict]]) -> List[Decimal]:
    """Длины сторон многоугольника (Decimal), в порядке обхода точек."""
    n = len(points)
    lengths = []
    for i in range(n):
        x1, y1 = _get_xy(points[i])
        x2, y2 = _get_xy(points[(i + 1) % n])
        dx = x2 - x1
        dy = y2 - y1
        lengths.append((dx * dx + dy * dy).sqrt())
    return lengths

def floor_area(points: List[Union[tuple, list, dict]]) -> Decimal:
    """
    Площадь многоугольника по формуле шнурования (Decimal).

    Аргументы:
        points: список точек в формате (x,y), [x,y] или {'x':x,'y':y}

    Возвращает:
        площадь (неотрицательная).
    """
    n = len(points)
    area = Decimal('0.0')
    for i in range(n):
        x1, y1 = _get_xy(points[i])
        x2, y2 = _get_xy(points[(i + 1) % n])
        area += x1 * y2 - x2 * y1
    return abs(area) / Decimal('2.0')

def perimeter(points: List[Union[tuple, list, dict]]) -> Decimal:
    """
    Периметр многоугольника (сумма длин сторон) с использованием Decimal.
    """
    return sum(side_lengths(points), Decimal('0.0'))

def _validate_openings(
    height: Decimal,
    openings: List[Dict[str, Any]],
    max_side_length: Decimal,
    wall_area_before: Decimal,
    total_opening_area: Decimal,
) -> None:
    """
    Валидация проёмов. Кидает ValueError с описанием ошибки.
    """
    for op in openings:
        width = to_decimal(op.get('width', 0))
        op_height = to_decimal(op.get('height', 0))
        op_type = op.get('type', 'unknown')
        type_ru = OPENING_TYPE_RU.get(op_type, 'проёма')

        if op_height > height:
            raise ValueError(
                f"Высота {type_ru} ({op_height:.2f} м) не может превышать высоту помещения ({height:.2f} м)."
            )
        if width > max_side_length:
            raise ValueError(
                f"Ширина {type_ru} ({width:.2f} м) не может превышать длину самой длинной стены ({max_side_length:.2f} м)."
            )

    if wall_area_before > 0 and total_opening_area >= wall_area_before:
        raise ValueError(
            f"Суммарная площадь проёмов ({total_opening_area:.2f} м²) не может быть больше или равна площади стен ({wall_area_before:.2f} м²)."
        )

def calculate_room_geometry(
    points: List[Union[tuple, list, dict]],
    height: Union[int, float, str, Decimal],
    openings: Optional[List[Union[dict, tuple]]] = None
) -> Dict[str, Decimal]:
    """
    Рассчитывает геометрию комнаты с валидацией проёмов.

    Возвращает:
        floor_area, ceiling_area, wall_area, perimeter, door_width_sum
    """
    # Приводим точки к единому формату (список кортежей (float, float))
    if points and isinstance(points[0], dict):
        pts = [(p['x'], p['y']) for p in points]
    else:
        pts = [(float(p[0]), float(p[1])) for p in points]

    # Длины сторон считаем один раз: нужны и для периметра, и для проверки ширины проёмов.
    sides = side_lengths(pts)
    max_side = max(sides) if sides else Decimal('0.0')
    perim = sum(sides, Decimal('0.0'))

    floor = floor_area(pts)

    if openings is None:
        openings = []
    openings_dict = []
    for op in openings:
        if isinstance(op, dict):
            openings_dict.append(op)
        else:
            op_type, w, h = op
            openings_dict.append({'type': op_type, 'width': w, 'height': h})

    total_opening_area = Decimal('0.0')
    for op in openings_dict:
        w = to_decimal(op.get('width', 0))
        h = to_decimal(op.get('height', 0))
        total_opening_area += w * h

    wall_area_before = perim * to_decimal(height)

    # Валидация проёмов (кидает ValueError)
    _validate_openings(
        height=to_decimal(height),
        openings=openings_dict,
        max_side_length=max_side,
        wall_area_before=wall_area_before,
        total_opening_area=total_opening_area
    )

    wall = wall_area_before - total_opening_area

    # Сумма ширин дверных проёмов — для плинтуса (периметр за вычетом дверей).
    # Окна не вычитаем: плинтус ими не прерывается (estimation-rules.md).
    door_width_sum = Decimal('0.0')
    for op in openings_dict:
        if op.get('type') == 'door':
            door_width_sum += to_decimal(op.get('width', 0))

    return {
        'floor_area': floor,
        'ceiling_area': floor,
        'wall_area': wall,
        'perimeter': perim,
        'door_width_sum': door_width_sum,
    }

def wall_area(
    points: List[Union[tuple, list, dict]],
    height: Union[int, float, str, Decimal],
    openings: Optional[List[Dict[str, Any]]] = None
) -> Decimal:
    """
    Площадь стен с вычетом проёмов.
    Обёртка над calculate_room_geometry для обратной совместимости.
    """
    result = calculate_room_geometry(points, height, openings)
    return result['wall_area']
