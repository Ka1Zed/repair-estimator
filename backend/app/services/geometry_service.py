
from typing import List, Union, Dict, Any, Optional
from decimal import Decimal, getcontext
import math

from app.core.norms import OTKOS_DEPTH_DEFAULT, CEILING_MULTILEVEL_STEP_HEIGHT_DEFAULT

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

def _segments_cross(a1: tuple, a2: tuple, b1: tuple, b2: tuple) -> bool:
    """Пересекаются ли отрезки a1a2 и b1b2 (включая касание точкой)."""
    def orient(p: tuple, q: tuple, r: tuple) -> Decimal:
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    def on_segment(p: tuple, q: tuple, r: tuple) -> bool:
        return (
            min(p[0], q[0]) <= r[0] <= max(p[0], q[0])
            and min(p[1], q[1]) <= r[1] <= max(p[1], q[1])
        )

    d1 = orient(b1, b2, a1)
    d2 = orient(b1, b2, a2)
    d3 = orient(a1, a2, b1)
    d4 = orient(a1, a2, b2)

    if ((d1 > 0 > d2) or (d1 < 0 < d2)) and ((d3 > 0 > d4) or (d3 < 0 < d4)):
        return True
    if d1 == 0 and on_segment(b1, b2, a1):
        return True
    if d2 == 0 and on_segment(b1, b2, a2):
        return True
    if d3 == 0 and on_segment(a1, a2, b1):
        return True
    if d4 == 0 and on_segment(a1, a2, b2):
        return True
    return False

def _validate_polygon(points: List[Union[tuple, list, dict]]) -> None:
    """
    Валидация контура комнаты. Кидает ValueError с описанием ошибки.

    Отвергает вырожденные контуры (меньше 3 точек, нулевая площадь — точки на
    одной прямой) и самопересечения («бабочка»): по такой геометрии смета
    считалась бы молча с floor_area = 0 при ненулевых стенах.
    """
    if len(points) < 3:
        raise ValueError("Контур комнаты должен содержать минимум 3 точки.")

    if floor_area(points) == 0:
        raise ValueError(
            "Контур комнаты вырожден: площадь равна нулю. "
            "Проверьте, что точки не лежат на одной прямой и стены не накладываются друг на друга."
        )

    coords = [_get_xy(p) for p in points]
    n = len(coords)
    for i in range(n):
        a1, a2 = coords[i], coords[(i + 1) % n]
        for j in range(i + 1, n):
            # Смежные стены общую вершину имеют законно — их не проверяем.
            if j == i + 1 or (i == 0 and j == n - 1):
                continue
            b1, b2 = coords[j], coords[(j + 1) % n]
            if _segments_cross(a1, a2, b1, b2):
                raise ValueError(
                    "Контур комнаты самопересекается: стены не должны пересекать друг друга. "
                    "Проверьте порядок точек."
                )

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

def _ceiling_area(
    floor: Decimal,
    perim: Decimal,
    ceiling_shape: Optional[Dict[str, Any]],
) -> Decimal:
    """
    Площадь потолка по форме (#357). ceiling_shape=None или type="flat" —
    плоский потолок, площадь равна проекции пола (прежнее поведение).

    - multilevel: ceiling_area = floor + perimeter × step_height_m × levels
      (верхние грани коробов ≈ проекция пола, добавляем только вертикальные
      грани коробов по периметру помещения на каждый уровень).
    - attic_slope: ceiling_area = floor / cos(slope_deg) (единая наклонная
      плоскость над всей проекцией пола).
    """
    if not ceiling_shape:
        return floor

    shape_type = ceiling_shape.get('type', 'flat')
    if shape_type == 'flat' or shape_type is None:
        return floor

    if shape_type == 'multilevel':
        levels = ceiling_shape.get('levels')
        levels = int(levels) if levels is not None else 1
        if levels < 1 or levels > 5:
            raise ValueError("Число уровней потолка должно быть от 1 до 5.")

        step_height = ceiling_shape.get('step_height_m')
        step_height = to_decimal(step_height) if step_height is not None else CEILING_MULTILEVEL_STEP_HEIGHT_DEFAULT
        if step_height <= 0 or step_height > 1:
            raise ValueError("Высота грани короба должна быть больше 0 и не более 1 м.")

        return floor + perim * step_height * Decimal(levels)

    if shape_type == 'attic_slope':
        slope_deg = ceiling_shape.get('slope_deg')
        slope_deg = to_decimal(slope_deg) if slope_deg is not None else Decimal('0')
        if slope_deg < 0 or slope_deg > 85:
            raise ValueError("Угол ската потолка должен быть от 0 до 85° включительно.")

        cos_slope = Decimal(str(math.cos(math.radians(float(slope_deg)))))
        return floor / cos_slope

    raise ValueError(f'Неизвестная форма потолка: "{shape_type}".')

def calculate_room_geometry(
    points: List[Union[tuple, list, dict]],
    height: Union[int, float, str, Decimal],
    openings: Optional[List[Union[dict, tuple]]] = None,
    ceiling_shape: Optional[Dict[str, Any]] = None,
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

    # Валидация контура (кидает ValueError): вырожденный или самопересекающийся
    # многоугольник дал бы смету с floor_area = 0 при ненулевых стенах.
    _validate_polygon(pts)

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
            # (type, width, height) или (type, width, height, depth)
            op_type, w, h = op[0], op[1], op[2]
            depth = op[3] if len(op) > 3 else None
            openings_dict.append({'type': op_type, 'width': w, 'height': h, 'depth': depth})

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

    # Площадь откосов проёмов (#191): отделываемая поверхность по периметру проёма
    # на глубину стены. Периметр откоса = ширина + 2×высота (верхняя грань + две
    # боковые; низ — подоконник/порог, в откос не входит). Глубина берётся из поля
    # depth проёма или дефолта по типу. Считается ОТДЕЛЬНО, в wall_area не входит.
    otkos_area = Decimal('0.0')
    for op in openings_dict:
        op_type = op.get('type', 'unknown')
        w = to_decimal(op.get('width', 0))
        h = to_decimal(op.get('height', 0))
        depth = op.get('depth')
        depth = to_decimal(depth) if depth is not None else OTKOS_DEPTH_DEFAULT.get(
            op_type, OTKOS_DEPTH_DEFAULT['unknown']
        )
        otkos_area += (w + 2 * h) * depth

    return {
        'floor_area': floor,
        'ceiling_area': _ceiling_area(floor, perim, ceiling_shape),
        'wall_area': wall,
        'perimeter': perim,
        'door_width_sum': door_width_sum,
        'otkos_area': otkos_area,
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
