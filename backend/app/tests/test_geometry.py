from decimal import Decimal
from app.services.geometry_service import (
    floor_area, perimeter, wall_area, calculate_room_geometry,
)


class TestGeometry:
    """Тесты для функций геометрии"""

    def test_rectangle_4x3(self):
        """Прямоугольник 4×3: площадь = 12, периметр = 14, высота 2.7 -> площадь стен = 37.8"""
        points = [(0,0), (4,0), (4,3), (0,3)]
        height = Decimal('2.7')
        
        area = floor_area(points)
        perim = perimeter(points)
        walls = wall_area(points, height)
        
        assert area == Decimal('12.0')
        assert perim == Decimal('14.0')
        assert walls == Decimal('37.8')

    def test_l_shaped_room(self):
        """
        Г-образная комната.
        Координаты (0,0), (5,0), (5,2), (3,2), (3,5), (0,5)
        Фигура — прямоугольник 5×5 с вырезанным квадратом 2×3 в правом верхнем углу.
        Площадь = 5*5 - 2*3 = 25 - 6 = 19.
        Периметр считаем вручную: 
        - по контуру: 5 + 2 + 2 + 3 + 2 + 3 + 2 + 5 = 24? Давайте пересчитаем.
          Обход: (0,0)->(5,0)=5; (5,0)->(5,2)=2; (5,2)->(3,2)=2; (3,2)->(3,5)=3;
          (3,5)->(0,5)=3; (0,5)->(0,0)=5. Итого 5+2+2+3+3+5 = 20.
          Проверка: на самом деле ещё есть внутренний угол, но периметр многоугольника — это внешний контур, он не имеет самопересечений, так что 20 — верно.
        Высота 3.0 -> площадь стен = 20 * 3 = 60.
        """
        points = [(0,0), (5,0), (5,2), (3,2), (3,5), (0,5)]
        height = Decimal('3.0')
        
        area = floor_area(points)
        perim = perimeter(points)
        walls = wall_area(points, height)
        
        assert area == Decimal('19.0')
        assert perim == Decimal('20.0')
        assert walls == Decimal('60.0')
    
    def test_triangle(self):
        """Прямоугольный треугольник 3×4: площадь = 6, периметр = 12 (3+4+5)"""
        points = [(0,0), (4,0), (0,3)]
        area = floor_area(points)
        perim = perimeter(points)
        assert area == Decimal('6.0')
        assert perim == Decimal('12.0')
    
    
    def test_zero_height(self):
        """Высота 0 -> площадь стен 0"""
        points = [(0,0), (2,0), (2,2), (0,2)]
        assert wall_area(points, Decimal('0.0')) == Decimal('0.0')

    def test_rectangle_with_openings(self):
        """Прямоугольник 4×3, высота 2.7, дверь 0.8×2.0, окно 1.5×1.4 -> стены = 34.1"""
        points = [(0,0), (4,0), (4,3), (0,3)]
        height = Decimal('2.7')
        openings = [
            {'type': 'door', 'width': 0.8, 'height': 2.0},
            {'type': 'window', 'width': 1.5, 'height': 1.4}
        ]
        walls = wall_area(points, height, openings)
        expected = Decimal('34.1')   # 37.8 - 1.6 - 2.1 = 34.1
        assert walls == expected

    def test_no_openings(self):
        """Без проёмов площадь стен = периметр * высота"""
        points = [(0,0), (4,0), (4,3), (0,3)]
        height = Decimal('2.7')
        walls = wall_area(points, height, [])
        expected = perimeter(points) * height
        assert walls == expected


class TestOtkosArea:
    """Площадь откосов проёмов (#191). Откос = (ширина + 2×высота) × глубина."""

    POINTS = [(0, 0), (4, 0), (4, 3), (0, 3)]
    HEIGHT = 2.7

    def test_default_depth_door_and_window(self):
        """Дефолтная глубина: дверь 0.15 м, окно 0.25 м.

        Дверь 0.8×2.0: (0.8 + 2×2.0)×0.15 = 4.8×0.15 = 0.72
        Окно 1.5×1.4: (1.5 + 2×1.4)×0.25 = 4.3×0.25 = 1.075
        Итого 1.795 м². В wall_area откос не входит — стены как раньше (34.1).
        """
        openings = [
            {'type': 'door', 'width': 0.8, 'height': 2.0},
            {'type': 'window', 'width': 1.5, 'height': 1.4},
        ]
        geom = calculate_room_geometry(self.POINTS, self.HEIGHT, openings)
        assert geom['otkos_area'] == Decimal('1.795')
        # Инвариант: откос не трогает площадь стен (полный проём вычтен как раньше).
        assert geom['wall_area'] == Decimal('34.1')

    def test_area_grows_with_depth(self):
        """При увеличении глубины откоса площадь откосов растёт."""
        base = [{'type': 'door', 'width': 0.8, 'height': 2.0}]
        deep = [{'type': 'door', 'width': 0.8, 'height': 2.0, 'depth': 0.30}]
        a_base = calculate_room_geometry(self.POINTS, self.HEIGHT, base)['otkos_area']
        a_deep = calculate_room_geometry(self.POINTS, self.HEIGHT, deep)['otkos_area']
        assert a_deep > a_base
        assert a_deep == Decimal('1.44')   # 4.8 × 0.30

    def test_no_openings_zero_otkos(self):
        """Без проёмов площадь откосов = 0."""
        geom = calculate_room_geometry(self.POINTS, self.HEIGHT, [])
        assert geom['otkos_area'] == Decimal('0')