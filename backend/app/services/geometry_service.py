
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

