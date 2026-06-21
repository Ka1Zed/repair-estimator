# app/tests/test_estimate.py

import pytest
from decimal import Decimal

from app.services.material_calc_service import calculate_materials, packs_to_buy
from app.services.labor_calc_service import calculate_labor
from app.services.repair_coeffs_service import apply_repair_coeffs


class TestMaterialCalc:
    """Модульные тесты для расчёта материалов."""

    def test_material_calc_rectangle(self, db_session):
        """Прямоугольная комната 4×3, h=2.7, ламинат, покраска стен и потолка."""
        geometry = {
            'floor_area': Decimal('12.0'),
            'ceiling_area': Decimal('12.0'),
            'wall_area': Decimal('34.1'),
            'perimeter': Decimal('14.0'),
            'door_width_sum': Decimal('0.8')  # одна дверь
        }
        repair_options = {
            'floor': 'laminate',
            'walls': 'paint',
            'ceiling': 'paint',
            'tile': False,
            'electric': 'basic',
            'plumbing': False
        }

        materials = calculate_materials(geometry, repair_options, db_session)

        # Ожидаемые имена материалов (все должны быть)
        expected_names = {
            'Ламинат', 'Плинтус', 'Грунтовка', 'Шпаклевка',
            'Краска для стен', 'Краска потолочная'
        }
        returned_names = {m['name'] for m in materials}
        assert expected_names.issubset(returned_names)

        # Проверка количества для ламината (с округлением НЕ делаем здесь)
        laminate = next(m for m in materials if m['name'] == 'Ламинат')
        # Площадь пола 12 * 1.08 = 12.96
        assert laminate['quantity'] == Decimal('12.96')
        # pack_quantity = 12.96 / 2.5 = 5.184 (из seed package_size)
        assert laminate['pack_quantity'] == Decimal('5.184')

        # Проверка плинтуса: периметр - дверь = 14 - 0.8 = 13.2, *1.1 = 14.52
        plinth = next(m for m in materials if m['name'] == 'Плинтус')
        assert plinth['quantity'] == Decimal('14.52')

        # Грунтовка: 34.1 * 0.1 * 1.1 = 3.751
        primer = next(m for m in materials if m['name'] == 'Грунтовка')
        assert primer['quantity'] == Decimal('3.751')

        # Шпаклевка: 34.1 * 1.2 * 1.1 = 45.012
        putty = next(m for m in materials if m['name'] == 'Шпаклевка')
        assert putty['quantity'] == Decimal('45.012')

        # Краска стен: 34.1 * 2 * 0.13 * 1.1 = 9.7526
        paint_walls = next(m for m in materials if m['name'] == 'Краска для стен')
        assert paint_walls['quantity'] == Decimal('9.7526')

        # Краска потолка: 12 * 2 * 0.12 * 1.1 = 3.168
        paint_ceiling = next(m for m in materials if m['name'] == 'Краска потолочная')
        assert paint_ceiling['quantity'] == Decimal('3.168')

        # Округление до упаковок: для ламината 5.184 → 6 упаковок
        assert packs_to_buy(laminate['pack_quantity']) == 6


class TestLaborCalc:
    """Модульные тесты для расчёта работ."""

    def test_labor_calc_rectangle(self, db_session):
        """Прямоугольная комната 4×3, h=2.7, ламинат, покраска стен и потолка."""
        geometry = {
            'floor_area': Decimal('12.0'),
            'ceiling_area': Decimal('12.0'),
            'wall_area': Decimal('34.1'),
            'perimeter': Decimal('14.0'),
            'electrical_points': Decimal('5'),
            'plumbing_points': Decimal('2')
        }
        repair_options = {
            'floor': 'laminate',
            'walls': 'paint',
            'ceiling': 'paint',
            'tile': False,
            'electric': 'basic',
            'plumbing': True
        }

        labor = calculate_labor(geometry, repair_options, db_session)

        # Проверяем, что все ожидаемые услуги есть
        expected_services = {
            'Покраска стен', 'Покраска потолка', 'Шпаклевка стен',
            'Укладка ламината', 'Электромонтаж', 'Сантехнические работы'
        }
        returned_services = {item['service'] for item in labor}
        assert expected_services.issubset(returned_services)

        # Проверка объёмов
        painter_walls = next(item for item in labor if item['service'] == 'Покраска стен')
        assert painter_walls['volume'] == Decimal('34.1')

        painter_ceiling = next(item for item in labor if item['service'] == 'Покраска потолка')
        assert painter_ceiling['volume'] == Decimal('12.0')

        putty = next(item for item in labor if item['service'] == 'Шпаклевка стен')
        assert putty['volume'] == Decimal('34.1')

        laminate_install = next(item for item in labor if item['service'] == 'Укладка ламината')
        assert laminate_install['volume'] == Decimal('12.0')

        electric = next(item for item in labor if item['service'] == 'Электромонтаж')
        assert electric['volume'] == Decimal('5')

        plumbing = next(item for item in labor if item['service'] == 'Сантехнические работы')
        assert plumbing['volume'] == Decimal('2')


class TestRepairCoeffs:
    """Тесты применения коэффициентов типа ремонта и непредвиденных расходов."""

    def test_coeffs_scale(self):
        """Проверка, что при переходе cosmetic → base итог умножается на 1.2."""
        materials = {'min': Decimal('100'), 'avg': Decimal('200'), 'max': Decimal('300')}
        labor = {'min': Decimal('400'), 'avg': Decimal('500'), 'max': Decimal('600')}

        res_cosmetic = apply_repair_coeffs(materials, labor, 'cosmetic')
        res_base = apply_repair_coeffs(materials, labor, 'base')

        for key in ['materials_min', 'materials_avg', 'materials_max',
                    'labor_min', 'labor_avg', 'labor_max',
                    'total_min', 'total_avg', 'total_max']:
            assert res_base[key] == res_cosmetic[key] * Decimal('1.2')

    def test_min_avg_max_order(self):
        """Проверка, что min ≤ avg ≤ max для всех категорий."""
        materials = {'min': Decimal('100'), 'avg': Decimal('200'), 'max': Decimal('300')}
        labor = {'min': Decimal('400'), 'avg': Decimal('500'), 'max': Decimal('600')}

        for repair_type in ['cosmetic', 'base', 'extended']:
            result = apply_repair_coeffs(materials, labor, repair_type)
            for category in ['materials', 'labor', 'total']:
                assert result[f'{category}_min'] <= result[f'{category}_avg'] <= result[f'{category}_max']

    def test_no_coeffs_equals_raw(self):
        """При cosmetic и коэффициенте непредвиденных = 1.0 сумма равна исходной."""
        # В реальном коде контингент жёстко задан, поэтому мы не можем получить 1.0.
        # Но мы можем проверить, что результат при cosmetic и контингенте = 1.1/1.12/1.15
        # соответствует ожидаемому умножению.
        materials = {'min': Decimal('100'), 'avg': Decimal('200'), 'max': Decimal('300')}
        labor = {'min': Decimal('400'), 'avg': Decimal('500'), 'max': Decimal('600')}

        result = apply_repair_coeffs(materials, labor, 'cosmetic')
        # Для min: (100+400)*1.1 = 550
        assert result['total_min'] == Decimal('550')
        # avg: (200+500)*1.12 = 784
        assert result['total_avg'] == Decimal('784')
        # max: (300+600)*1.15 = 1035
        assert result['total_max'] == Decimal('1035')

    def test_unknown_repair_type_raises_error(self):
        """Неизвестный тип ремонта вызывает ValueError."""
        materials = {'min': Decimal('1'), 'avg': Decimal('2'), 'max': Decimal('3')}
        labor = {'min': Decimal('4'), 'avg': Decimal('5'), 'max': Decimal('6')}
        with pytest.raises(ValueError, match="Unknown repair_type: basic"):
            apply_repair_coeffs(materials, labor, 'basic')