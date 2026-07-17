# app/tests/test_estimate.py

import json
from decimal import Decimal
from itertools import product
from pathlib import Path

from app.services.material_calc_service import (
    calculate_materials, calculate_engineering_materials, packs_to_buy,
)
from app.services.labor_calc_service import (
    calculate_labor, calculate_engineering_labor, calculate_rough_labor,
)
from app.services.geometry_service import calculate_room_geometry
from app.services.price_aggregator_service import get_price, get_labor_price

# Источник правды по типам комнат и допустимым отделкам (docs/room-types.json).
ROOM_TYPES_JSON = Path(__file__).resolve().parents[3] / "docs" / "room-types.json"


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

    def test_ceiling_paint_adds_primer_and_putty(self, db_session):
        """ceiling=paint (#380) кладёт грунт и шпаклёвку потолка симметрично стенам,
        от ceiling_area (а не только краску, как было)."""
        geometry = {
            'floor_area': Decimal('12.0'),
            'ceiling_area': Decimal('15.0'),
            'wall_area': Decimal('34.1'),
            'perimeter': Decimal('14.0'),
            'door_width_sum': Decimal('0.8'),
        }
        opts = {'floor': None, 'walls': None, 'ceiling': 'paint'}

        materials = calculate_materials(geometry, opts, db_session)
        by_name = {m['name']: m for m in materials}
        for name in ('Грунтовка', 'Шпаклевка стартовая', 'Шпаклевка финишная', 'Краска потолочная'):
            assert name in by_name, f"нет материала «{name}» для потолка"

        # Грунт потолка: 15.0 * 1 слой * 0.12 * 1.1 = 1.98 (без wall_condition — у потолка его нет)
        assert by_name['Грунтовка']['quantity'] == Decimal('1.98')
        # Стартовая шпаклёвка потолка: 15.0 * 5.0 * 1.1 = 82.5, без масштабирования кривизны
        assert by_name['Шпаклевка стартовая']['quantity'] == Decimal('82.5')
        # Финишная: 15.0 * 1.0 * 1.1 = 16.5
        assert by_name['Шпаклевка финишная']['quantity'] == Decimal('16.5')

    def test_ceiling_primer_two_coats_independent_of_walls(self, db_session):
        """works.ceiling.primer_two_coats удваивает только грунт потолка, не затрагивая
        стены, и наоборот (#380) — общий флаг на repair_options не должен перетирать
        выбор одной из поверхностей при одновременной покраске стен и потолка."""
        geometry = {
            'floor_area': Decimal('12.0'),
            'ceiling_area': Decimal('12.0'),
            'wall_area': Decimal('34.1'),
            'perimeter': Decimal('14.0'),
            'door_width_sum': Decimal('0.8'),
        }
        opts = {'floor': None, 'walls': 'paint', 'ceiling': 'paint'}

        def primers(mats):
            # _selections кладёт грунт стен раньше грунта потолка — порядок стабилен.
            found = [m for m in mats if m['name'] == 'Грунтовка']
            assert len(found) == 2
            return found  # (стены, потолок)

        base_wall, base_ceiling = primers(calculate_materials(geometry, opts, db_session))
        c2_wall, c2_ceiling = primers(calculate_materials(
            geometry, {**opts, 'ceiling_primer_two_coats': True}, db_session,
        ))
        w2_wall, w2_ceiling = primers(calculate_materials(
            geometry, {**opts, 'primer_two_coats': True}, db_session,
        ))

        # ceiling_primer_two_coats удваивает только потолок, стены не трогает.
        assert c2_wall['quantity'] == base_wall['quantity']
        assert c2_ceiling['quantity'] == base_ceiling['quantity'] * Decimal('2')

        # primer_two_coats (стеновой) удваивает только стены, потолок не трогает.
        assert w2_wall['quantity'] == base_wall['quantity'] * Decimal('2')
        assert w2_ceiling['quantity'] == base_ceiling['quantity']

    def test_unknown_material_slug_skipped_not_crashed(self, db_session):
        """Опечатка/расхождение slug в seed → материал тихо пропускается (как раньше
        было с name), расчёт остальных строк не падает (#278)."""
        from app.db.models import Material

        primer = db_session.query(Material).filter(Material.slug == "primer").first()
        primer.slug = "primer_TYPO"
        db_session.commit()
        try:
            geometry = {
                'floor_area': Decimal('12.0'), 'ceiling_area': Decimal('12.0'),
                'wall_area': Decimal('34.1'), 'perimeter': Decimal('14.0'),
                'door_width_sum': Decimal('0.8'),
            }
            repair_options = {'floor': None, 'walls': 'paint', 'ceiling': None}

            materials = calculate_materials(geometry, repair_options, db_session)

            names = {m['name'] for m in materials}
            assert 'Грунтовка' not in names          # slug разошёлся — строка пропущена
            assert 'Шпаклевка стартовая' in names     # остальные материалы посчитаны как обычно
            assert 'Краска для стен' in names
        finally:
            primer.slug = "primer"
            db_session.commit()


class TestFinishVariants:
    """Варианты материала по уровню комплектации (#331): tier выбирает конкретный
    SKU (finish_key/variant_tier — см. conftest.variant_materials), а не только
    границу вилки одного и того же товара."""

    GEOM = {
        'floor_area': Decimal('12.0'), 'ceiling_area': Decimal('12.0'),
        'wall_area': Decimal('34.1'), 'perimeter': Decimal('14.0'),
        'door_width_sum': Decimal('0.8'),
    }

    def test_tier_selects_different_sku(self, db_session):
        """tier=min/avg/max на floor.laminate — три РАЗНЫХ material_id/name/package_size."""
        repair_options = {'floor': 'laminate', 'walls': None, 'ceiling': None}

        by_tier = {}
        for tier in ("min", "avg", "max"):
            materials = calculate_materials(self.GEOM, repair_options, db_session, tier=tier)
            laminate = next(m for m in materials if m['unit'] == 'м²')
            by_tier[tier] = laminate

        assert by_tier['min']['name'] == 'Ламинат эконом'
        assert by_tier['avg']['name'] == 'Ламинат'
        assert by_tier['max']['name'] == 'Ламинат премиум'
        # Разные material_id → в агрегации (B1-5) это разные строки сметы,
        # а не одна строка с другой ценой.
        assert len({by_tier[t]['material_id'] for t in by_tier}) == 3
        assert by_tier['min']['package_size'] == 1.5
        assert by_tier['avg']['package_size'] == 2.0
        assert by_tier['max']['package_size'] == 2.5

    def test_fallback_to_nearest_tier_when_variant_missing(self, db_session):
        """Позиция без варианта запрошенного tier не выпадает — резолвится в avg."""
        ceiling_only = {'floor': None, 'walls': None, 'ceiling': 'paint'}
        materials_min = calculate_materials(self.GEOM, ceiling_only, db_session, tier="min")
        ceiling_paint = next((m for m in materials_min if m['name'] == 'Краска потолочная'), None)
        assert ceiling_paint is not None  # ceiling.paint не имеет min-варианта → fallback на avg

        sockets_max = calculate_engineering_materials(
            sockets=3, lights=0, cable_m=0, pipe_m=0, db=db_session, tier="max",
        )
        socket = next((m for m in sockets_max if m['name'] == 'Розетка'), None)
        assert socket is not None  # socket не имеет max-варианта → fallback на avg


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

    def test_finish_labor_carries_stage(self, db_session):
        """Каждая отделочная строка помечена стадией: покраска — finish, шпаклёвка — pre_finish (#190)."""
        geometry = {
            'floor_area': Decimal('12.0'),
            'ceiling_area': Decimal('12.0'),
            'wall_area': Decimal('34.1'),
            'perimeter': Decimal('14.0'),
        }
        labor = calculate_labor(geometry, {'walls': 'paint'}, db_session)
        by_service = {item['service']: item for item in labor}
        assert by_service['Покраска стен']['stage'] == 'finish'
        assert by_service['Шпаклевка стен']['stage'] == 'pre_finish'

    def test_ceiling_finish_labor_carries_stage(self, db_session):
        """Покраска потолка — finish, шпаклёвка потолка — pre_finish (#380), симметрично
        стенам (test_finish_labor_carries_stage)."""
        geometry = {
            'floor_area': Decimal('12.0'),
            'ceiling_area': Decimal('12.0'),
            'wall_area': Decimal('34.1'),
            'perimeter': Decimal('14.0'),
        }
        labor = calculate_labor(geometry, {'ceiling': 'paint'}, db_session)
        by_service = {item['service']: item for item in labor}
        assert by_service['Покраска потолка']['stage'] == 'finish'
        assert by_service['Шпаклевка потолка']['stage'] == 'pre_finish'
        assert by_service['Шпаклевка потолка']['volume'] == Decimal('12.0')

    def test_stretch_ceiling_is_block_not_multiplier(self, db_session):
        """Натяжной потолок (#191) — блок потолочника: полотно + закладные + ниша.

        Полотно считается по ceiling_area (12), а не множителем к floor_area;
        закладные — по числу точек, ниша — по погонажу, отдельными строками.
        """
        geometry = {
            'floor_area': Decimal('12.0'),
            'ceiling_area': Decimal('12.0'),
            'wall_area': Decimal('34.1'),
            'perimeter': Decimal('14.0'),
        }
        finish_options = {
            'ceiling': 'stretch',
            'ceiling_light_points': 3,
            'ceiling_curtain_niche_m': Decimal('2.0'),
        }
        labor = calculate_labor(geometry, finish_options, db_session)
        by_service = {item['service']: item for item in labor}

        assert {'Монтаж натяжного потолка', 'Закладная под светильник',
                'Ниша под карниз'}.issubset(set(by_service))
        # Полотно — по площади потолка, не скрытый множитель площади пола.
        assert by_service['Монтаж натяжного потолка']['volume'] == Decimal('12.0')
        assert by_service['Закладная под светильник']['volume'] == Decimal('3')
        assert by_service['Ниша под карниз']['volume'] == Decimal('2.0')
        # Все строки блока — у потолочника.
        for name in ('Монтаж натяжного потолка', 'Закладная под светильник', 'Ниша под карниз'):
            assert by_service[name]['specialist'] == 'Потолочник'

    def test_stretch_ceiling_without_niche_skips_niche_line(self, db_session):
        """Ниша под карниз считается только при погонаже > 0."""
        geometry = {'floor_area': Decimal('12.0'), 'ceiling_area': Decimal('12.0'),
                    'wall_area': Decimal('34.1'), 'perimeter': Decimal('14.0')}
        labor = calculate_labor(
            geometry, {'ceiling': 'stretch', 'ceiling_light_points': 2}, db_session
        )
        services = {item['service'] for item in labor}
        assert 'Ниша под карниз' not in services
        assert 'Закладная под светильник' in services

    def test_otkos_line_when_walls_finished(self, db_session):
        """Откосы (#191) — отдельная строка при отделке стен и наличии проёмов."""
        geometry = {
            'floor_area': Decimal('12.0'),
            'ceiling_area': Decimal('12.0'),
            'wall_area': Decimal('34.1'),
            'perimeter': Decimal('14.0'),
            'otkos_area': Decimal('1.795'),
        }
        labor = calculate_labor(geometry, {'walls': 'paint'}, db_session)
        by_service = {item['service']: item for item in labor}
        assert 'Отделка откосов' in by_service
        assert by_service['Отделка откосов']['volume'] == Decimal('1.795')
        assert by_service['Отделка откосов']['stage'] == 'finish'

    def test_otkos_skipped_without_wall_finish(self, db_session):
        """Без отделки стен откосы не считаются, даже если проёмы есть."""
        geometry = {
            'floor_area': Decimal('12.0'),
            'ceiling_area': Decimal('12.0'),
            'wall_area': Decimal('34.1'),
            'perimeter': Decimal('14.0'),
            'otkos_area': Decimal('1.795'),
        }
        labor = calculate_labor(geometry, {'floor': 'laminate'}, db_session)
        assert 'Отделка откосов' not in {item['service'] for item in labor}


class TestRoughLabor:
    """Черновые работы при scope=rough_and_finish (#190)."""

    GEOM = {
        'floor_area': Decimal('12.0'),
        'ceiling_area': Decimal('12.0'),
        'wall_area': Decimal('34.1'),
        'perimeter': Decimal('14.0'),
    }

    def test_bathroom_rough_works(self, db_session):
        """Санузел с плиткой: демонтаж, выравнивание, стяжка, гидроизоляция, грунт — все rough."""
        rough = calculate_rough_labor(
            self.GEOM, {'floor': 'tile', 'walls': 'tile'}, 'bathroom', db_session,
        )
        by_service = {item['service']: item for item in rough}

        expected = {'Демонтаж', 'Выравнивание стен', 'Стяжка пола', 'Гидроизоляция', 'Грунтование'}
        assert expected.issubset(set(by_service))
        # Все черновые строки помечены стадией rough.
        assert all(item['stage'] == 'rough' for item in rough)

        # Жёсткие связки по объёму: демонтаж/стяжка/гидроизоляция — по полу, выравнивание — по стенам.
        assert by_service['Демонтаж']['volume'] == Decimal('12.0')
        assert by_service['Стяжка пола']['volume'] == Decimal('12.0')
        assert by_service['Гидроизоляция']['volume'] == Decimal('12.0')
        assert by_service['Выравнивание стен']['volume'] == Decimal('34.1')

    def test_dry_room_without_tile_skips_waterproof(self, db_session):
        """Жилая комната без плитки: гидроизоляции нет, но демонтаж/выравнивание/стяжка есть."""
        rough = calculate_rough_labor(
            self.GEOM, {'floor': 'laminate', 'walls': 'paint'}, 'living', db_session,
        )
        services = {item['service'] for item in rough}
        assert 'Гидроизоляция' not in services
        assert {'Демонтаж', 'Выравнивание стен', 'Стяжка пола'}.issubset(services)

    def test_dry_room_with_tile_floor_skips_waterproof(self, db_session):
        """Плитка на полу в сухой комнате гидроизоляцию не тянет — только мокрая зона."""
        rough = calculate_rough_labor(
            self.GEOM, {'floor': 'tile', 'walls': 'paint'}, 'living', db_session,
        )
        services = {item['service'] for item in rough}
        assert 'Гидроизоляция' not in services

    def test_ceiling_paint_pulls_ceiling_primer(self, db_session):
        """Покраска потолка тянет грунт потолка на черновой стадии (#380), симметрично
        стенам (walls тянут S_LEVEL_WALLS+S_PRIMER), но не выравнивание — у потолка
        своей операции выравнивания в MVP нет."""
        rough = calculate_rough_labor(
            self.GEOM, {'walls': None, 'ceiling': 'paint', 'floor': None}, 'living', db_session,
        )
        by_service = {item['service']: item for item in rough}
        assert 'Грунтование потолка' in by_service
        assert by_service['Грунтование потолка']['stage'] == 'rough'
        assert by_service['Грунтование потолка']['volume'] == Decimal('12.0')
        # Стен нет (walls=None) — их выравнивание/грунт не должны появиться.
        assert 'Выравнивание стен' not in by_service
        assert 'Грунтование' not in by_service

    def test_stretch_ceiling_skips_ceiling_primer(self, db_session):
        """Натяжной потолок не тянет грунт — своей подготовки основания не требует (#380)."""
        rough = calculate_rough_labor(
            self.GEOM, {'walls': None, 'ceiling': 'stretch', 'floor': None}, 'living', db_session,
        )
        assert 'Грунтование потолка' not in {item['service'] for item in rough}


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


class TestFinishOptionsCoverage:
    """Каждая отделка из docs/room-types.json должна иметь расчётную базу: свой
    материал/работу с seed-ценой. Иначе смета молча занижается (#231)."""

    GEOM = {
        'floor_area': Decimal('12.0'),
        'ceiling_area': Decimal('12.0'),
        'wall_area': Decimal('34.1'),
        'perimeter': Decimal('14.0'),
        'door_width_sum': Decimal('0.8'),
    }

    @staticmethod
    def _room_types():
        with open(ROOM_TYPES_JSON, encoding="utf-8") as file:
            return json.load(file)["roomTypes"]

    def test_every_room_type_finish_combo_is_priced(self, db_session):
        """Для каждой комбинации room_type × (floor,walls,ceiling) смета отдаёт
        ненулевые строки материалов и работ, и у каждой есть seed-цена
        (нет source «нет цены» / молчаливо потерянных строк работ)."""
        for rt_key, rt in self._room_types().items():
            for floor, walls, ceiling in product(rt["floor"], rt["walls"], rt["ceiling"]):
                opts = {"floor": floor, "walls": walls, "ceiling": ceiling}
                ctx = f"{rt_key} {opts}"

                materials = calculate_materials(self.GEOM, opts, db_session)
                labor = calculate_labor(self.GEOM, opts, db_session)

                assert materials, f"нет материалов: {ctx}"
                assert labor, f"нет работ: {ctx}"

                for m in materials:
                    assert m["quantity"] > 0, f"нулевое количество {m['name']}: {ctx}"
                    # get_price → seed-цена; None означало бы source «нет цены» в смете.
                    assert get_price(m["name"], db=db_session) is not None, \
                        f"нет цены материала {m['name']}: {ctx}"
                for job in labor:
                    # Работа без цены молча выпадает из сметы (endpoint: continue).
                    assert get_labor_price(job["service"], db=db_session) is not None, \
                        f"нет цены работы {job['service']}: {ctx}"

    def test_wallpaper_has_gluing_work(self, db_session):
        """living + обои: в работах есть «Поклейка обоев» (раньше = 0)."""
        labor = calculate_labor(self.GEOM, {"walls": "wallpaper"}, db_session)
        services = {j["service"] for j in labor}
        assert "Поклейка обоев" in services
        assert get_labor_price("Поклейка обоев", db=db_session) is not None

    def test_parquet_maps_to_own_material_and_work(self, db_session):
        """Паркет: отдельный материал «Паркетная доска» и работа «Укладка паркета»,
        не молчаливый fallback на ламинат."""
        opts = {"floor": "parquet"}
        materials = {m["name"] for m in calculate_materials(self.GEOM, opts, db_session)}
        services = {j["service"] for j in calculate_labor(self.GEOM, opts, db_session)}
        assert "Паркетная доска" in materials
        assert "Укладка паркета" in services
        assert "Укладка ламината" not in services

    def test_moisture_paint_maps_to_own_material(self, db_session):
        """Влагостойкая краска на стенах — свой материал, не «Краска для стен»."""
        opts = {"walls": "moisture_paint"}
        materials = {m["name"] for m in calculate_materials(self.GEOM, opts, db_session)}
        assert "Краска влагостойкая" in materials
        assert "Краска для стен" not in materials

    def test_stretch_ceiling_is_a_priced_work(self, db_session):
        """bathroom + натяжной потолок: работа «Монтаж натяжного потолка» с ценой > 0,
        отдельной строки материала нет (материал в цене работы)."""
        opts = {"ceiling": "stretch"}
        labor = calculate_labor(self.GEOM, opts, db_session)
        by_service = {j["service"]: j for j in labor}
        assert "Монтаж натяжного потолка" in by_service
        assert by_service["Монтаж натяжного потолка"]["volume"] == Decimal("12.0")
        price = get_labor_price("Монтаж натяжного потолка", db=db_session)
        assert price is not None and price.price_avg > 0
        # Натяжной не даёт строки материала.
        assert calculate_materials(self.GEOM, opts, db_session) == []


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

        # Грунтовка и стартовая шпаклёвка суммируются из обеих комнат: покраска стен+потолка
        # (комната1) и обои (комната2) все тянут подготовку основания (#325, #380).
        # Финишная шпаклёвка — из покраски (комната1, стены и потолок), под обои она не
        # нужна (полотно скрывает огрехи).
        primer = next((v for k, v in aggregated.items() if v['name'] == 'Грунтовка'), None)
        assert primer is not None
        # Комната1 стены: 34.1*0.12*1.1=4.5012; комната1 потолок: 12.0*0.12*1.1=1.584;
        # комната2 стены (обои): 48.6*0.12*1.1=6.4152. Итого 12.5004.
        assert primer['quantity'] == Decimal('12.5004')

        putty = next((v for k, v in aggregated.items() if v['name'] == 'Шпаклевка финишная'), None)
        assert putty is not None
        # Комната1 стены: 34.1*1.0*1.1=37.51; комната1 потолок: 12.0*1.0*1.1=13.2. Итого 50.71.
        assert putty['quantity'] == Decimal('50.71')

        putty_start = next((v for k, v in aggregated.items() if v['name'] == 'Шпаклевка стартовая'), None)
        assert putty_start is not None
        # Комната1 стены: 34.1*5.0*1.1=187.55; комната1 потолок: 12.0*5.0*1.1=66.0;
        # комната2 стены (обои): 48.6*5.0*1.1=267.3. Итого 520.85.
        assert putty_start['quantity'] == Decimal('520.85')
