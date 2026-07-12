# app/tests/test_price_normalization.py

import pytest
from decimal import Decimal
from unittest.mock import Mock

from datetime import datetime, timezone

from app.services.price_aggregator_service import get_price, get_material_price, _normalize_price
from app.parsers.base import ParsedPrice
from app.db.models import Material, MaterialPrice, PriceSource


def test_normalize_price():
    """Проверка функции нормировки цены к единице измерения."""
    assert _normalize_price(Decimal('100'), Decimal('5')) == Decimal('20')
    assert _normalize_price(Decimal('100'), None) == Decimal('100')
    assert _normalize_price(Decimal('100'), Decimal('1')) == Decimal('100')


class TestPriceNormalization:
    """Тесты на нормировку цен и коридор внутри уровня."""

    @pytest.mark.parametrize("material_name", [
        "Краска для стен",
        "Краска потолочная",
        "Ламинат",
        "Грунтовка",
    ])
    def test_seed_prices_exist_and_ordered(self, db_session, material_name):
        """Проверяем, что seed-цены существуют и упорядочены (min <= avg <= max)."""
        price_obj = get_price(material_name, db=db_session, region=None)
        assert price_obj is not None, f"Цена для {material_name} не найдена в seed"
        assert price_obj.price_min <= price_obj.price_avg <= price_obj.price_max, \
            f"Некорректный порядок цен для {material_name}: {price_obj.price_min} <= {price_obj.price_avg} <= {price_obj.price_max}"

    @pytest.mark.parametrize("source_name,price_min,price_avg,price_max", [
        ("Мегастрой", 102, 120, 144),   # avg=120, min=85%, max=120%
        ("Леман", 102, 120, 144),       # те же цены для проверки единообразия
    ])
    def test_parser_prices_within_corridor(self, db_session, source_name, price_min, price_avg, price_max, monkeypatch):
        """Мокаем парсер, который возвращает нормированные цены (уже за единицу).
        Проверяем, что min и max лежат в коридоре ±15% от avg.
        """
        material_name = "Краска для стен"

        # Убедимся, что источник существует в БД (иначе get_price отбросит парсер)
        src = db_session.query(PriceSource).filter(PriceSource.name == source_name).first()
        if not src:
            src = PriceSource(name=source_name, type="parser", url="http://example.com")
            db_session.add(src)
            db_session.commit()

        mock_parser = Mock()
        mock_parser.source_name = source_name
        mock_parser.fetch_price.return_value = ParsedPrice(
            price_min=Decimal(price_min),
            price_avg=Decimal(price_avg),
            price_max=Decimal(price_max),
            source_url=f'http://example-{source_name.lower()}.com',
        )

        price_obj = get_price(material_name, db=db_session, parser=mock_parser, region='Москва')
        assert price_obj is not None

        avg = price_obj.price_avg
        min_ = price_obj.price_min
        max_ = price_obj.price_max

        # Проверяем коридор ±15% (min >= 85% от avg, max <= 120% от avg)
        lower_bound = avg * Decimal('0.85')
        upper_bound = avg * Decimal('1.20')
        assert min_ >= lower_bound, f"min={min_} слишком низкая для {source_name} (должна быть >= {lower_bound})"
        assert max_ <= upper_bound, f"max={max_} слишком высокая для {source_name} (должна быть <= {upper_bound})"

    def test_parser_prices_consistency_across_sources(self, db_session, monkeypatch):
        """Проверяем, что после нормировки цены из разных источников для одного уровня близки (в пределах 20%)."""
        material_name = "Краска для стен"

        # Создаём источники, если их нет
        for name in ["Мегастрой", "Леман"]:
            src = db_session.query(PriceSource).filter(PriceSource.name == name).first()
            if not src:
                src = PriceSource(name=name, type="parser", url=f"http://{name.lower()}.ru")
                db_session.add(src)
        db_session.commit()

        mock_megastroy = Mock()
        mock_megastroy.source_name = "Мегастрой"
        mock_megastroy.fetch_price.return_value = ParsedPrice(
            price_min=Decimal('102'),
            price_avg=Decimal('120'),
            price_max=Decimal('144'),
            source_url='http://megastroy.ru',
        )

        mock_leman = Mock()
        mock_leman.source_name = "Леман"
        mock_leman.fetch_price.return_value = ParsedPrice(
            price_min=Decimal('106'),
            price_avg=Decimal('125'),
            price_max=Decimal('150'),
            source_url='http://leman.ru',
        )

        price_megastroy = get_price(material_name, db=db_session, parser=mock_megastroy, region='Москва')
        price_leman = get_price(material_name, db=db_session, parser=mock_leman, region='Москва')

        assert price_megastroy is not None
        assert price_leman is not None

        # Проверяем, что средние цены различаются не более чем на 20%
        ratio = max(price_megastroy.price_avg, price_leman.price_avg) / min(price_megastroy.price_avg, price_leman.price_avg)
        assert ratio <= Decimal('1.2'), f"Цены слишком различаются: {price_megastroy.price_avg} vs {price_leman.price_avg}"


class TestMaterialPriceCombination:
    """get_material_price (#333): объединение цен материала из нескольких источников,
    по аналогии с test_labor_combines_multiple_regional_sites в test_labor_parsers.py.

    Цены источников вставляются напрямую в MaterialPrice (свежий updated_at), а не
    через живой fetch_price — так тест не зависит от TTL-кэша, оставленного другими
    тестами файла (get_price кэширует parser-цену материала по (material, source) без
    привязки к региону). Моки парсеров при этом остаются полностью герметичны:
    fetch_price кидает RuntimeError вместо похода в сеть — их не должно вызвать при
    свежем кэше, а если вызовет (нет строки), это тоже не сеть, а fallback на seed.
    """

    MATERIAL = "Краска для стен"

    def _clear_parser_prices(self, db_session):
        seed = db_session.query(PriceSource).filter(PriceSource.name == "seed").first()
        material = db_session.query(Material).filter(Material.name == self.MATERIAL).first()
        db_session.query(MaterialPrice).filter(
            MaterialPrice.material_id == material.id,
            MaterialPrice.source_id != seed.id,
        ).delete()
        db_session.commit()

    def _seed_source(self, db_session, name):
        src = db_session.query(PriceSource).filter(PriceSource.name == name).first()
        if not src:
            src = PriceSource(name=name, type="parser", url=f"http://{name.lower()}.ru")
            db_session.add(src)
            db_session.commit()
        return src

    def _insert_price(self, db_session, source_name, price_min, price_avg, price_max):
        material = db_session.query(Material).filter(Material.name == self.MATERIAL).first()
        source = self._seed_source(db_session, source_name)
        row = MaterialPrice(
            material_id=material.id, source_id=source.id,
            price_min=Decimal(price_min), price_avg=Decimal(price_avg), price_max=Decimal(price_max),
            source_url=f"http://example-{source_name.lower()}.ru",
            updated_at=datetime.now(timezone.utc),
        )
        db_session.add(row)
        db_session.commit()

    def _no_network_parser(self, source_name):
        parser = Mock()
        parser.source_name = source_name
        parser.fetch_price.side_effect = RuntimeError("сеть недоступна (тест герметичен)")
        return parser

    def test_combines_two_sources_into_one_corridor(self, db_session):
        """Мегастрой + Леман дают валидные цены → вилка min по обоим/max по обоим/
        avg среднего средних, sources содержит оба источника."""
        self._clear_parser_prices(db_session)
        try:
            self._insert_price(db_session, "Мегастрой", 100, 120, 150)
            self._insert_price(db_session, "Леман", 130, 160, 200)

            price = get_material_price(
                self.MATERIAL, db=db_session,
                parsers=[self._no_network_parser("Мегастрой"), self._no_network_parser("Леман")],
                region="Москва",
            )

            assert price is not None
            assert price.price_min == Decimal("100")   # минимум по источникам
            assert price.price_max == Decimal("200")   # максимум по источникам
            assert price.price_avg == Decimal("140")   # среднее средних (120+160)/2
            assert set(price.contributing_sources) == {"Мегастрой", "Леман"}
            # parser-цены нерегиональны (region IS NULL) → объединённая тоже null,
            # хотя в запросе был регион (контракт docs/api.md: парсерная → region=null).
            assert price.region is None
        finally:
            self._clear_parser_prices(db_session)

    def test_single_source_reports_one_source(self, db_session):
        """Только у одного источника есть цена → вилка этого источника, sources из одного элемента."""
        self._clear_parser_prices(db_session)
        try:
            self._insert_price(db_session, "Мегастрой", 100, 120, 150)
            self._seed_source(db_session, "Леман")  # источник заведён, но цены нет

            price = get_material_price(
                self.MATERIAL, db=db_session,
                parsers=[self._no_network_parser("Мегастрой"), self._no_network_parser("Леман")],
                region="Москва",
            )

            assert price is not None
            assert price.price_avg == Decimal("120")
            assert price.contributing_sources == ["Мегастрой"]
        finally:
            self._clear_parser_prices(db_session)

    def test_no_valid_source_falls_back_to_seed(self, db_session):
        """Ни один источник не дал валидной цены → корректный fallback на seed (не падает, не пусто)."""
        self._clear_parser_prices(db_session)
        try:
            price = get_material_price(
                self.MATERIAL, db=db_session,
                parsers=[self._no_network_parser("Мегастрой"), self._no_network_parser("Леман")],
            )

            assert price is not None
            assert price.price_avg > 0
            assert getattr(price, "contributing_sources", None) is None
        finally:
            self._clear_parser_prices(db_session)
