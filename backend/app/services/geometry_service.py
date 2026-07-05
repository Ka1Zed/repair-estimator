
from typing import List, Union, Dict, Any, Optional
from decimal import Decimal, getcontext

getcontext().prec = 28

OPENING_TYPE_RU = {
    'door': 'двери',
    'window': 'окна',
    'unknown': 'проёма'
}

DEFAULT_REVEAL_DEPTH_WINDOW = Decimal('0.20')
DEFAULT_REVEAL_DEPTH_DOOR = Decimal('0.15')

def to_decimal(value: Union[int, float, str, Decimal, None]) -> Decimal:
    """Преобразует значение в Decimal, избегая ошибок float."""
    if value is None:
        return Decimal(0)
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    return Decimal(value)

def floor_area(points: List[Union[tuple, list, dict]]) -> Decimal:
    """
    Площадь многоугольника по формуле шнурования (Decimal).
    
    Аргументы:
        points: список точек в формате (x,y), [x,y] или {'x':x,'y':y}
    
    Возвращает:
        площадь (неотрицательная).
    """
    n = len(points)
    def get_xy(p):
        if isinstance(p, dict):
            return to_decimal(p['x']), to_decimal(p['y'])
        else:
            return to_decimal(p[0]), to_decimal(p[1])
    area = Decimal('0.0')
    for i in range(n):
        x1, y1 = get_xy(points[i])
        x2, y2 = get_xy(points[(i + 1) % n])
        area += x1 * y2 - x2 * y1
    return abs(area) / Decimal('2.0')

def perimeter(points: List[Union[tuple, list, dict]]) -> Decimal:
    """
    Периметр многоугольника (сумма длин сторон) с использованием Decimal.
    """
    n = len(points)
    def get_xy(p):
        if isinstance(p, dict):
            return to_decimal(p['x']), to_decimal(p['y'])
        else:
            return to_decimal(p[0]), to_decimal(p[1])
    perim = Decimal('0.0')
    for i in range(n):
        x1, y1 = get_xy(points[i])
        x2, y2 = get_xy(points[(i + 1) % n])
        dx = x2 - x1
        dy = y2 - y1
        distance = (dx * dx + dy * dy).sqrt()
        perim += distance
    return perim

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

    # Вычисляем длины сторон в Decimal
    side_lengths = []
    n = len(pts)
    for i in range(n):
        x1, y1 = Decimal(str(pts[i][0])), Decimal(str(pts[i][1]))
        x2, y2 = Decimal(str(pts[(i + 1) % n][0])), Decimal(str(pts[(i + 1) % n][1]))
        dx = x2 - x1
        dy = y2 - y1
        length = (dx * dx + dy * dy).sqrt()
        side_lengths.append(length)
    max_side = max(side_lengths) if side_lengths else Decimal('0.0')
    perim = sum(side_lengths, Decimal('0.0'))

    floor = floor_area(pts)

    if openings is None:
        openings = []
    openings_dict = []
    for op in openings:
        if isinstance(op, dict):
            openings_dict.append(op)
        else:
            if len(op) == 4:
                op_type, width, height, reveal_depth = op
            else:
                op_type, width, height = op
                reveal_depth = None
            entry = {'type': op_type, 'width': width, 'height': height}
            if reveal_depth is not None:
                entry['reveal_depth'] = reveal_depth
            openings_dict.append(entry)

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
    door_width_sum = Decimal('0.0')
    for op in openings_dict:
        if op.get('type') == 'door':
            door_width_sum += to_decimal(op.get('width', 0))

    reveal_area = Decimal('0.0')
    reveal_length = Decimal('0.0')
    for op in openings_dict:
        w = to_decimal(op.get('width', 0))
        h = to_decimal(op.get('height', 0))
        depth = to_decimal(op.get('reveal_depth', 0))  # to_decimal теперь обрабатывает None
        if depth == 0:
            if op.get('type') == 'window':
                depth = DEFAULT_REVEAL_DEPTH_WINDOW
            elif op.get('type') == 'door':
                depth = DEFAULT_REVEAL_DEPTH_DOOR
        reveal_area += depth * (Decimal('2') * h + w)
        reveal_length += Decimal('2') * h + w
    return {
        'floor_area': floor,
        'ceiling_area': floor,
        'wall_area': wall,
        'perimeter': perim,
        'door_width_sum': door_width_sum,
        'reveal_area': reveal_area,
        'reveal_length': reveal_length,
    }

def wall_area(
    points: List[Union[tuple, list, dict]],
    height: Union[int, float, str, Decimal],
    openings: Optional[List[Dict[str, Any]]] = None
) -> Decimal:
    """
    Площадь стен с вычетом проёмов.
    """
    result = calculate_room_geometry(points, height, openings)
    return result['wall_area']

