# app/tests/test_estimate.py

from decimal import Decimal

from app.services.material_calc_service import (
    calculate_materials, calculate_engineering_materials, packs_to_buy,
)
from app.services.labor_calc_service import calculate_labor, calculate_engineering_labor
from app.services.geometry_service import calculate_room_geometry


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
            'electric': 'basic',
            'plumbing': False
        }

        materials = calculate_materials(geometry, repair_options, db_session)

        # Ожидаемые имена материалов (все должны быть)
        expected_names = {
            'Ламинат', 'Плинтус', 'Грунтовка',
            'Шпаклевка стартовая', 'Шпаклевка финишная',
            'Краска для стен', 'Краска потолочная'
        }
        returned_names = {m['name'] for m in materials}
        assert expected_names.issubset(returned_names)

        # Проверка количества для ламината (с округлением НЕ делаем здесь)
        laminate = next(m for m in materials if m['name'] == 'Ламинат')
        # Площадь пола 12 * 1.15 = 13.8
        assert laminate['quantity'] == Decimal('13.8')
        # Детализация (#176): base_quantity (до запаса) * waste_factor == quantity
        assert laminate['base_quantity'] == Decimal('12.0')
        assert laminate['waste_factor'] == Decimal('1.15')
        assert laminate['base_quantity'] * laminate['waste_factor'] == laminate['quantity']
        # Проверяем дробное значение pack_quantity до агрегации — ceil делается в B1-5
        # package_size=2.0 -> 13.8 / 2.0 = 6.9
        assert laminate['pack_quantity'] == Decimal('6.9')
        assert packs_to_buy(laminate['pack_quantity']) == 7  # демонстрация, что ceil работает

        # Проверка плинтуса: периметр - дверь = 14 - 0.8 = 13.2, *1.05 = 13.86
        plinth = next(m for m in materials if m['name'] == 'Плинтус')
        assert plinth['quantity'] == Decimal('13.86')

        # Грунтовка: 34.1 * 0.12 * 1.1 = 4.5012
        primer = next(m for m in materials if m['name'] == 'Грунтовка')
        assert primer['quantity'] == Decimal('4.5012')

        # Шпаклёвка разнесена на стартовую и финишную (paint-walls включает обе).
        # Стартовая: 34.1 * 5.0 * 1.1 = 187.55
        putty_start = next(m for m in materials if m['name'] == 'Шпаклевка стартовая')
        assert putty_start['quantity'] == Decimal('187.55')
        # Финишная: 34.1 * 1.0 * 1.1 = 37.51
        putty_finish = next(m for m in materials if m['name'] == 'Шпаклевка финишная')
        assert putty_finish['quantity'] == Decimal('37.51')

        # Краска стен: 34.1 * 2 * 0.13 * 1.1 = 9.7526
        paint_walls = next(m for m in materials if m['name'] == 'Краска для стен')
        assert paint_walls['quantity'] == Decimal('9.7526')

        # Краска потолка: 12 * 2 * 0.15 * 1.1 = 3.96
        paint_ceiling = next(m for m in materials if m['name'] == 'Краска потолочная')
        assert paint_ceiling['quantity'] == Decimal('3.96')

    def test_wallpaper_pattern_adds_30_percent(self, db_session):
        """Обои под рисунок (wallpaper_pattern=True) дают на 30% больше рулонов, чем гладкие."""
        geometry = {
            'floor_area': Decimal('20.0'),
            'ceiling_area': Decimal('20.0'),
            'wall_area': Decimal('48.6'),
            'perimeter': Decimal('18.0'),
            'door_width_sum': Decimal('1.2'),
        }
        base_opts = {'floor': None, 'walls': 'wallpaper', 'ceiling': None}

        plain = calculate_materials(geometry, base_opts, db_session)
        patterned = calculate_materials(
            geometry, {**base_opts, 'wallpaper_pattern': True}, db_session
        )

        plain_wp = next(m for m in plain if m['name'] == 'Обои')
        patterned_wp = next(m for m in patterned if m['name'] == 'Обои')

        # Гладкие: 48.6 * 0.2 * 1.1 = 10.692; под рисунок: ×1.3 = 13.8996
        assert plain_wp['quantity'] == Decimal('10.692')
        assert patterned_wp['quantity'] == Decimal('13.8996')
        assert patterned_wp['quantity'] == plain_wp['quantity'] * Decimal('1.3')

    def test_primer_two_coats_doubles_primer(self, db_session):
        """primer_two_coats=True кладёт грунт в 2 слоя — ровно ×2 к расходу грунтовки."""
        geometry = {
            'floor_area': Decimal('20.0'),
            'ceiling_area': Decimal('20.0'),
            'wall_area': Decimal('48.6'),
            'perimeter': Decimal('18.0'),
            'door_width_sum': Decimal('1.2'),
        }
        base_opts = {'floor': None, 'walls': 'paint', 'ceiling': None}

        one_coat = calculate_materials(geometry, base_opts, db_session)
        two_coats = calculate_materials(
            geometry, {**base_opts, 'primer_two_coats': True}, db_session
        )

        primer_1 = next(m for m in one_coat if m['name'] == 'Грунтовка')
        primer_2 = next(m for m in two_coats if m['name'] == 'Грунтовка')

        # 1 слой: 48.6 * 0.12 * 1.1 = 6.4152; 2 слоя: ×2 = 12.8304
        assert primer_1['quantity'] == Decimal('6.4152')
        assert primer_2['quantity'] == Decimal('12.8304')
        assert primer_2['quantity'] == primer_1['quantity'] * Decimal('2')

    def test_wall_condition_scales_starting_putty(self, db_session):
        """wall_condition масштабирует только стартовую шпаклёвку; финишная неизменна."""
        geometry = {
            'floor_area': Decimal('20.0'),
            'ceiling_area': Decimal('20.0'),
            'wall_area': Decimal('48.6'),
            'perimeter': Decimal('18.0'),
            'door_width_sum': Decimal('1.2'),
        }
        base_opts = {'floor': None, 'walls': 'paint', 'ceiling': None}

        no_field = calculate_materials(geometry, base_opts, db_session)
        normal = calculate_materials(geometry, {**base_opts, 'wall_condition': 'normal'}, db_session)
        even = calculate_materials(geometry, {**base_opts, 'wall_condition': 'even'}, db_session)
        uneven = calculate_materials(geometry, {**base_opts, 'wall_condition': 'uneven'}, db_session)

        def start(mats):
            return next(m for m in mats if m['name'] == 'Шпаклевка стартовая')['quantity']

        def finish(mats):
            return next(m for m in mats if m['name'] == 'Шпаклевка финишная')['quantity']

        normal_qty = start(normal)
        # Дефолт (поле отсутствует) эквивалентен "normal": 48.6 * 5.0 * 1.1 = 267.3
        assert normal_qty == Decimal('267.3')
        assert start(no_field) == normal_qty
        # even ×0.6, uneven ×1.6 к норме.
        assert start(even) == normal_qty * Decimal('0.6')
        assert start(uneven) == normal_qty * Decimal('1.6')

        # Финишная шпаклёвка одинакова во всех вариантах: 48.6 * 1.0 * 1.1 = 53.46
        assert finish(no_field) == Decimal('53.46')
        assert finish(normal) == finish(no_field)
        assert finish(even) == finish(no_field)
        assert finish(uneven) == finish(no_field)



class TestLaborCalc:
    """Модульные тесты для расчёта работ."""

    def test_labor_calc_rectangle(self, db_session):
        """Прямоугольная комната 4×3, h=2.7, ламинат, покраска стен и потолка (только отделка)."""
        geometry = {
            'floor_area': Decimal('12.0'),
            'ceiling_area': Decimal('12.0'),
            'wall_area': Decimal('34.1'),
            'perimeter': Decimal('14.0'),
        }
        finish_options = {
            'floor': 'laminate',
            'walls': 'paint',
            'ceiling': 'paint',
        }

        labor = calculate_labor(geometry, finish_options, db_session)

        # Отделочные работы есть; инженерка здесь не считается (отдельный путь).
        expected_services = {
            'Покраска стен', 'Покраска потолка', 'Шпаклевка стен', 'Укладка ламината',
        }
        returned_services = {item['service'] for item in labor}
        assert expected_services.issubset(returned_services)
        assert 'Электромонтаж' not in returned_services
        assert 'Сантехнические работы' not in returned_services

        painter_walls = next(item for item in labor if item['service'] == 'Покраска стен')
        assert painter_walls['volume'] == Decimal('34.1')

        painter_ceiling = next(item for item in labor if item['service'] == 'Покраска потолка')
        assert painter_ceiling['volume'] == Decimal('12.0')

        putty = next(item for item in labor if item['service'] == 'Шпаклевка стен')
        assert putty['volume'] == Decimal('34.1')

        laminate_install = next(item for item in labor if item['service'] == 'Укладка ламината')
        assert laminate_install['volume'] == Decimal('12.0')


class TestEngineeringCalc:
    """Электрика/сантехника по явным числам works (#222)."""

    def test_engineering_labor_by_explicit_numbers(self, db_session):
        """Работы электрики/сантехники берут объём из явных чисел, а не из геометрии."""
        labor = calculate_engineering_labor(
            sockets=6, lights=2, cable_m=Decimal('48'),
            plumbing_points=3, pipe_m=Decimal('9'), db=db_session,
        )
        by_service = {item['service']: item for item in labor}

        assert by_service['Монтаж розетки']['volume'] == Decimal('6')
        assert by_service['Монтаж розетки']['unit'] == 'шт'
        assert by_service['Монтаж светильника']['volume'] == Decimal('2')
        assert by_service['Прокладка кабеля']['volume'] == Decimal('48')
        assert by_service['Прокладка кабеля']['unit'] == 'м'
        assert by_service['Сантехнические работы']['volume'] == Decimal('3')
        assert by_service['Монтаж труб']['volume'] == Decimal('9')

    def test_engineering_materials_units_and_waste(self, db_session):
        """Штучные позиции без запаса, погонаж с waste_factor; труба не идёт как плинтус."""
        mats = calculate_engineering_materials(
            sockets=6, lights=2, cable_m=Decimal('50'), pipe_m=Decimal('10'), db=db_session,
        )
        by_name = {m['name']: m for m in mats}

        # Штучные — ровно число из запроса, без запаса.
        assert by_name['Розетка']['quantity'] == Decimal('6')
        assert by_name['Розетка']['base_quantity'] == Decimal('6')
        assert by_name['Розетка']['waste_factor'] == Decimal('1')
        assert by_name['Светильник']['quantity'] == Decimal('2')
        # Погонаж — метраж × waste_factor 1.1 (не через плинтусную ветку quantity_of).
        assert by_name['Кабель электрический']['quantity'] == Decimal('55.0')
        assert by_name['Кабель электрический']['base_quantity'] == Decimal('50')
        assert by_name['Кабель электрический']['waste_factor'] == Decimal('1.1')
        assert by_name['Труба водопроводная']['quantity'] == Decimal('11.0')
        assert by_name['Труба водопроводная']['base_quantity'] == Decimal('10')
        # Труба: package_size 2 (хлыст) → округление до хлыстов на агрегации.
        assert packs_to_buy(by_name['Труба водопроводная']['pack_quantity']) == 6  # ceil(11/2)

    def test_engineering_zero_skips_lines(self, db_session):
        """Нулевые числа (выключенная группа) не добавляют строк."""
        assert calculate_engineering_labor(0, 0, 0, 0, 0, db_session) == []
        assert calculate_engineering_materials(0, 0, 0, 0, db_session) == []


class TestLShape:
    def test_l_shaped_room_materials(self, db_session):
        """Г-образная комната (невыпуклый многоугольник) – проверка геометрии и материалов."""
        points = [
            (0, 0), (4, 0), (4, 2), (2, 2), (2, 4), (0, 4)
        ]
        geometry = calculate_room_geometry(
            points=points,
            height=2.7,
            openings=[{"type": "door", "width": 0.8, "height": 2.0}]
        )

        # calculate_room_geometry не возвращает door_width_sum — добавляем вручную для расчёта плинтуса
        geometry['door_width_sum'] = Decimal('0.8')

        repair_options = {
            'floor': 'laminate',
            'walls': 'paint',
            'ceiling': 'paint',
            'electric': 'basic',
            'plumbing': False
        }

        materials = calculate_materials(geometry, repair_options, db_session)

        # Площадь пола: 4×4 с вырезом 2×2 = 12
        assert geometry['floor_area'] == Decimal('12.0')
        # Периметр: (0,0)→(4,0)=4, (4,0)→(4,2)=2, (4,2)→(2,2)=2, (2,2)→(2,4)=2, (2,4)→(0,4)=2, (0,4)→(0,0)=4 → итого 16
        assert geometry['perimeter'] == Decimal('16.0')

        # Ламинат: площадь 12 * 1.15 = 13.8, package_size=2.0 -> 6.9 (дробно)
        laminate = next(m for m in materials if m['name'] == 'Ламинат')
        assert laminate['pack_quantity'] == Decimal('6.9')

        # Плинтус: периметр (16) - дверь (0.8) = 15.2, *1.05 = 15.96
        plinth = next(m for m in materials if m['name'] == 'Плинтус')
        assert plinth['quantity'] == Decimal('15.96')

        # Проверяем, что есть грунтовка, шпаклёвка, краска
        primer = next(m for m in materials if m['name'] == 'Грунтовка')
        assert primer['quantity'] > 0

class TestDifferentRooms:
    """Тесты агрегации материалов из нескольких разных комнат."""

    def test_aggregation_different_rooms(self, db_session):
        """Проверка агрегации материалов из двух разных комнат."""
        # Комната 1: 4×3, ламинат, покраска стен и потолка
        geom1 = {
            'floor_area': Decimal('12.0'),
            'ceiling_area': Decimal('12.0'),
            'wall_area': Decimal('34.1'),
            'perimeter': Decimal('14.0'),
            'door_width_sum': Decimal('0.8')
        }
        opts1 = {
            'floor': 'laminate',
            'walls': 'paint',
            'ceiling': 'paint',
            'electric': 'basic',
            'plumbing': False
        }
        materials1 = calculate_materials(geom1, opts1, db_session)

        # Комната 2: 5×4, линолеум, обои (без потолка)
        geom2 = {
            'floor_area': Decimal('20.0'),
            'ceiling_area': Decimal('20.0'),
            'wall_area': Decimal('48.6'),  # периметр 18, высота 2.7 -> 48.6
            'perimeter': Decimal('18.0'),
            'door_width_sum': Decimal('1.2')
        }
        opts2 = {
            'floor': 'linoleum',
            'walls': 'wallpaper',
            'ceiling': None,
            'electric': 'basic',
            'plumbing': False
        }
        materials2 = calculate_materials(geom2, opts2, db_session)

        # Агрегируем все материалы вручную
        aggregated = {}
        for mat in materials1 + materials2:
            mid = mat['material_id']
            if mid not in aggregated:
                aggregated[mid] = {
                    'name': mat['name'],
                    'unit': mat['unit'],
                    'quantity': Decimal(0),
                    'pack_quantity': Decimal(0),
                }
            aggregated[mid]['quantity'] += mat['quantity']
            if mat.get('pack_quantity') is not None:
                aggregated[mid]['pack_quantity'] += mat['pack_quantity']

        # Проверяем, что ламинат есть только из первой комнаты
        laminate = next((v for k, v in aggregated.items() if v['name'] == 'Ламинат'), None)
        assert laminate is not None
        assert laminate['quantity'] == Decimal('13.8')  # 12 * 1.15

        # Линолеум — только из второй
        linoleum = next((v for k, v in aggregated.items() if v['name'] == 'Линолеум'), None)
        assert linoleum is not None
        assert linoleum['quantity'] == Decimal('21.0')  # 20 * 1.0 * 1.05 (waste_factor=1.05 в seed)

        # Обои — только из второй (wallpaper)
        wallpaper = next((v for k, v in aggregated.items() if v['name'] == 'Обои'), None)
        assert wallpaper is not None
        # consumption_per_m2=0.2, waste=1.1 -> 48.6 * 0.2 * 1.1 = 10.692
        assert wallpaper['quantity'] == Decimal('10.692')

        # Проверяем, что краска для стен суммируется (из первой комнаты только)
        paint_walls = next((v for k, v in aggregated.items() if v['name'] == 'Краска для стен'), None)
        assert paint_walls is not None
        # Только комната1: 34.1 * 2 * 0.13 * 1.1 = 9.7526
        assert paint_walls['quantity'] == Decimal('9.7526')

        # Плинтус суммируется из обеих комнат (разные значения)
        plinth = next((v for k, v in aggregated.items() if v['name'] == 'Плинтус'), None)
        assert plinth is not None
        # Комната1: (14-0.8)*1.05 = 13.86
        # Комната2: (18-1.2)*1.05 = 17.64
        # Итого: 31.5
        assert plinth['quantity'] == Decimal('31.5')

        # Проверяем, что грунтовка и шпаклёвка есть только из первой (где стены красятся)
        primer = next((v for k, v in aggregated.items() if v['name'] == 'Грунтовка'), None)
        assert primer is not None
        assert primer['quantity'] == Decimal('4.5012')  # 34.1 * 0.12 * 1.1

        putty = next((v for k, v in aggregated.items() if v['name'] == 'Шпаклевка финишная'), None)
        assert putty is not None
        assert putty['quantity'] == Decimal('37.51')  # 34.1 * 1.0 * 1.1

        putty_start = next((v for k, v in aggregated.items() if v['name'] == 'Шпаклевка стартовая'), None)
        assert putty_start is not None
        assert putty_start['quantity'] == Decimal('187.55')  # 34.1 * 5.0 * 1.1
