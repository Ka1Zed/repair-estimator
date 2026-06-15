from decimal import Decimal
from app.services.geometry_service import floor_area, perimeter, wall_area


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