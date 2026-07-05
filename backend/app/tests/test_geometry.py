from decimal import Decimal
from app.services.geometry_service import floor_area, perimeter, wall_area
from decimal import Decimal
from app.services.geometry_service import calculate_room_geometry

class TestReveal:
    """Тесты для расчёта откосов."""

    def test_reveal_defaults(self):
        """Проверка площади откосов с дефолтными глубинами."""
        points = [(0,0), (4,0), (4,3), (0,3)]
        height = 2.7
        openings = [
            {"type": "window", "width": 1.4, "height": 1.5},   # дефолт 0.20
            {"type": "door", "width": 0.9, "height": 2.1}      # дефолт 0.15
        ]
        result = calculate_room_geometry(points, height, openings)

        # Ожидаемая площадь откосов для окна: 0.20 * (2*1.5 + 1.4) = 0.20 * 4.4 = 0.88
        # Для двери: 0.15 * (2*2.1 + 0.9) = 0.15 * 5.1 = 0.765
        # Сумма = 1.645
        expected_reveal_area = Decimal('1.645')
        assert result['reveal_area'] == expected_reveal_area

        # Погонаж: для окна (2*1.5 + 1.4) = 4.4; для двери (2*2.1 + 0.9) = 5.1; сумма = 9.5
        expected_reveal_length = Decimal('9.5')
        assert result['reveal_length'] == expected_reveal_length

    def test_reveal_custom_depth(self):
        """Проверка с явно заданной глубиной откоса."""
        points = [(0,0), (5,0), (5,4), (0,4)]
        height = 2.8
        openings = [
            {"type": "window", "width": 1.2, "height": 1.4, "reveal_depth": 0.3}
        ]
        result = calculate_room_geometry(points, height, openings)

        # Площадь: 0.3 * (2*1.4 + 1.2) = 0.3 * 4.0 = 1.2
        assert result['reveal_area'] == Decimal('1.2')
        # Погонаж: 2*1.4 + 1.2 = 4.0
        assert result['reveal_length'] == Decimal('4.0')

    def test_reveal_no_openings(self):
        """При отсутствии проёмов откосы должны быть нулевыми."""
        points = [(0,0), (3,0), (3,2), (0,2)]
        height = 2.5
        result = calculate_room_geometry(points, height, [])
        assert result['reveal_area'] == Decimal('0')
        assert result['reveal_length'] == Decimal('0')

    def test_wall_area_unchanged_by_reveal(self):
        """Наличие откосов не должно менять wall_area."""
        points = [(0,0), (4,0), (4,3), (0,3)]
        height = 2.7
        openings = [{"type": "window", "width": 1.4, "height": 1.5}]
        result_without = calculate_room_geometry(points, height, [])
        result_with = calculate_room_geometry(points, height, openings)
        assert result_with['wall_area'] == result_without['wall_area'] - Decimal('2.1')  # 1.4*1.5




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