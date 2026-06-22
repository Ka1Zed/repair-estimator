
from decimal import Decimal, getcontext
from typing import List, Union

# Устанавливаем точность Decimal (достаточно для большинства задач)
getcontext().prec = 28

def to_decimal(value: Union[int, float, str, Decimal]) -> Decimal:
    """Преобразует значение в Decimal, избегая ошибок float."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        # Преобразуем через строку, чтобы избежать двоичных артефактов
        return Decimal(str(value))
    return Decimal(value)

def floor_area(points: List[Union[tuple, list, dict]]) -> Decimal:
    """
    Площадь многоугольника по формуле шнурования (Decimal).
    
    Аргументы:
        points: список точек, каждая точка в формате:
                (x, y), [x, y] или {'x': x, 'y': y}
    
    Возвращает:
        площадь (неотрицательная).
    """
    n = len(points)
    
    def get_xy(p):
        if isinstance(p, dict):
            return to_decimal(p['x']), to_decimal(p['y'])
        else:
            # предполагаем, что p — это кортеж или список из двух элементов
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
    
    Аргументы:
        points: список точек (формат как выше).
    
    Возвращает:
        периметр.
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
        # квадратный корень из суммы квадратов
        distance = (dx * dx + dy * dy).sqrt()
        perim += distance
    return perim

def wall_area(points: List[Union[tuple, list, dict]], height: Union[int, float, str, Decimal], openings=None) -> Decimal:
    """
    Площадь стен = периметр × высота (Decimal).
    
    Аргументы:
        points: список точек основания.
        height: высота потолка.
    
    Возвращает:
        площадь стен.
    """
    if openings is None:
        openings = []
    perim = perimeter(points)
    wall_area_before = perim * to_decimal(height)
    # Вычитаем площади проёмов
    opening_area = Decimal('0.0')
    for opening in openings:
        # opening может быть словарём или объектом с полями width, height
        w = opening.get('width') if isinstance(opening, dict) else opening.width
        h = opening.get('height') if isinstance(opening, dict) else opening.height
        opening_area += to_decimal(w) * to_decimal(h)
    return wall_area_before - opening_area

def calculate_room_geometry(points, height, openings=None):
    """
    Рассчитывает геометрию комнаты по точкам многоугольника и высоте.
    """
    # Приводим points к единому формату (список кортежей)
    if points and isinstance(points[0], dict):
        pts = [(p['x'], p['y']) for p in points]
    else:
        pts = [(float(p[0]), float(p[1])) for p in points]  # гарантируем числовой тип

    # Вычисляем площадь пола и периметр
    floor = floor_area(pts)
    perim = perimeter(pts)

    # Преобразуем openings в список словарей для wall_area
    if openings is None:
        openings = []
    openings_dict = []
    for op in openings:
        if isinstance(op, dict):
            openings_dict.append(op)
        else:
            # ожидаем кортеж (type, width, height)
            _, w, h = op
            openings_dict.append({'width': w, 'height': h})

    wall = wall_area(pts, height, openings_dict)

    return {
        'floor_area': floor,
        'ceiling_area': floor,   # потолок равен полу
        'wall_area': wall,
        'perimeter': perim
    }