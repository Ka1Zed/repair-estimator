from fastapi import HTTPException, status
from typing import List, Union, Dict, Any, Optional
import math
from decimal import Decimal, getcontext

getcontext().prec = 28

def to_decimal(value: Union[int, float, str, Decimal]) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    return Decimal(value)

def floor_area(points: List[Union[tuple, list, dict]]) -> Decimal:
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
    for op in openings:
        width = to_decimal(op.get('width', 0))
        op_height = to_decimal(op.get('height', 0))
        op_type = op.get('type', 'unknown')

        if op_height > height:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Высота {op_type}а ({op_height:.2f} м) не может превышать высоту помещения ({height:.2f} м)."
            )
        if width > max_side_length:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Ширина {op_type}а ({width:.2f} м) не может превышать длину самой длинной стены ({max_side_length:.2f} м)."
            )

    # Проверяем только если площадь стен положительная
    if wall_area_before > 0 and total_opening_area >= wall_area_before:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Суммарная площадь проёмов ({total_opening_area:.2f} м²) не может быть больше или равна площади стен ({wall_area_before:.2f} м²)."
        )

def calculate_room_geometry(
    points: List[Union[tuple, list, dict]],
    height: Union[int, float, str, Decimal],
    openings: Optional[List[Union[dict, tuple]]] = None
) -> Dict[str, Decimal]:
    if points and isinstance(points[0], dict):
        pts = [(p['x'], p['y']) for p in points]
    else:
        pts = [(float(p[0]), float(p[1])) for p in points]

    side_lengths = []
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        dx = x2 - x1
        dy = y2 - y1
        side_lengths.append(math.hypot(dx, dy))
    max_side = Decimal(str(max(side_lengths)))
    perim = Decimal(str(sum(side_lengths)))
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

    _validate_openings(
        height=to_decimal(height),
        openings=openings_dict,
        max_side_length=max_side,
        wall_area_before=wall_area_before,
        total_opening_area=total_opening_area
    )

    wall = wall_area_before - total_opening_area

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
    result = calculate_room_geometry(points, height, openings)
    return result['wall_area']