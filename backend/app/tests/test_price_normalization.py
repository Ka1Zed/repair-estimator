# app/tests/test_price_normalization.py

import pytest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

from datetime import datetime, timezone

from app.services.price_aggregator_service import (
    get_price, get_material_price, _normalize_price, _select_regional_parsers,
)
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
        # region=None — источник без городской привязки (#345); Mock() без spec
        # иначе подставил бы авто-атрибут вместо None и сломал бы кэш-lookup в get_price.
        mock_parser.region = None
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
        mock_megastroy.region = None  # #345 — см. комментарий выше про Mock() без spec
        mock_megastroy.fetch_price.return_value = ParsedPrice(
            price_min=Decimal('102'),
            price_avg=Decimal('120'),
            price_max=Decimal('144'),
            source_url='http://megastroy.ru',
        )

        mock_leman = Mock()
        mock_leman.source_name = "Леман"
        mock_leman.region = None  # #345 — см. комментарий выше про Mock() без spec
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

    def _insert_price(self, db_session, source_name, price_min, price_avg, price_max, region=None):
        material = db_session.query(Material).filter(Material.name == self.MATERIAL).first()
        source = self._seed_source(db_session, source_name)
        row = MaterialPrice(
            material_id=material.id, source_id=source.id, region=region,
            price_min=Decimal(price_min), price_avg=Decimal(price_avg), price_max=Decimal(price_max),
            source_url=f"http://example-{source_name.lower()}.ru",
            updated_at=datetime.now(timezone.utc),
        )
        db_session.add(row)
        db_session.commit()

    def _no_network_parser(self, source_name, *, region=None, covered_cities=None):
        parser = Mock()
        parser.source_name = source_name
        # region/covered_cities=None по умолчанию — источник без городской
        # привязки (#345); Mock() без spec иначе подставил бы авто-атрибут
        # вместо None и сломал бы кэш-lookup в get_price/_select_regional_parsers.
        parser.region = region
        parser.covered_cities = covered_cities
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
            # #348: представитель — Мегастрой (его avg 120 не хуже Лемана-160 по
            # близости к 140, выигрывает тай-брейк первым в rows) и он же дал price_min
            # → min_source не дублируем (null). price_max дал Леман → его источник/ссылка
            # видны отдельно от source/source_url представителя.
            assert price.min_source_id is None
            assert price.min_source_url is None
            assert price.max_source_url == "http://example-леман.ru"
        finally:
            self._clear_parser_prices(db_session)

    def test_combine_attributes_min_and_max_to_different_sources_than_representative(self, db_session):
        """Когда ни минимум, ни максимум вилки не пришёлся на представителя —
        обе границы должны сослаться на СВОИ источники, а не молчать/дублировать
        source_url представителя (#348, основной сценарий issue: разные карточки
        товара для эконом-/премиум-границы)."""
        self._clear_parser_prices(db_session)
        try:
            self._insert_price(db_session, "Мегастрой", 100, 150, 155)   # представитель (avg ближе к 167)
            self._insert_price(db_session, "Леман", 90, 200, 210)        # даёт price_min
            self._seed_source(db_session, "Третий")
            self._insert_price(db_session, "Третий", 95, 150, 300)       # даёт price_max

            price = get_material_price(
                self.MATERIAL, db=db_session,
                parsers=[
                    self._no_network_parser("Мегастрой"),
                    self._no_network_parser("Леман"),
                    self._no_network_parser("Третий"),
                ],
                region="Москва",
            )

            assert price is not None
            assert price.price_min == Decimal("90")
            assert price.price_max == Decimal("300")
            # Представитель — Мегастрой (avg 150 и avg Третьего=150 равноудалены от 167,
            # тай-брейк выигрывает первый по rows — Мегастрой).
            assert price.source_url == "http://example-мегастрой.ru"
            assert price.min_source_url == "http://example-леман.ru"
            assert price.max_source_url == "http://example-третий.ru"
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

    # --- Региональные источники материалов (#345) ---

    def test_parser_cache_addressed_by_parser_own_region_not_by_request(self, db_session):
        """Кэш парсера адресуется (материал, источник, region САМОГО парсера), не
        аргументом region у get_price: Леман-Казань (region=None) и Леман-Москва
        (region="Москва") — общий source_id "Леман", разные строки в кэше."""
        self._clear_parser_prices(db_session)
        try:
            self._insert_price(db_session, "Леман", 100, 120, 150, region=None)
            self._insert_price(db_session, "Леман", 200, 250, 300, region="Москва")

            kazan = get_price(self.MATERIAL, db=db_session, parser=self._no_network_parser("Леман", region=None))
            moscow = get_price(self.MATERIAL, db=db_session, parser=self._no_network_parser("Леман", region="Москва"))

            assert kazan is not None and kazan.price_avg == Decimal("120") and kazan.region is None
            assert moscow is not None and moscow.price_avg == Decimal("250") and moscow.region == "Москва"
        finally:
            self._clear_parser_prices(db_session)

    def test_regional_source_excludes_default_sources_for_its_city(self, db_session):
        """Город с выделенным региональным источником (Леман-Москва, covered_cities)
        не должен получать в вилку цену источника без городской привязки (Мегастрой —
        физически только Казань, #345) — тот вообще не должен вызываться для Москвы."""
        self._clear_parser_prices(db_session)
        try:
            self._insert_price(db_session, "Мегастрой", 100, 120, 150, region=None)
            self._insert_price(db_session, "Леман", 200, 250, 300, region="Москва")

            price = get_material_price(
                self.MATERIAL, db=db_session,
                parsers=[
                    self._no_network_parser("Мегастрой"),
                    self._no_network_parser("Леман", region="Москва", covered_cities=frozenset({"Москва"})),
                ],
                region="Москва",
            )

            assert price is not None
            assert price.contributing_sources == ["Леман"]
            assert price.price_avg == Decimal("250")
            assert price.region == "Москва"
        finally:
            self._clear_parser_prices(db_session)

    def test_default_sources_used_when_no_regional_source_covers_city(self, db_session):
        """Город без выделенного регионального источника (напр. Казань) — как раньше,
        участвуют все источники без covered_cities (регресс не внесён, #345)."""
        self._clear_parser_prices(db_session)
        try:
            self._insert_price(db_session, "Мегастрой", 100, 120, 150, region=None)
            self._insert_price(db_session, "Леман", 200, 250, 300, region="Москва")

            price = get_material_price(
                self.MATERIAL, db=db_session,
                parsers=[
                    self._no_network_parser("Мегастрой"),
                    self._no_network_parser("Леман", region="Москва", covered_cities=frozenset({"Москва"})),
                ],
                region="Казань",
            )

            assert price is not None
            # Ни один covered_cities не совпал с "Казань" → берём только
            # источники без городской привязки (только Мегастрой в этом наборе).
            assert price.contributing_sources == ["Мегастрой"]
            assert price.price_avg == Decimal("120")
        finally:
            self._clear_parser_prices(db_session)


class TestSelectRegionalParsers:
    """_select_regional_parsers (#345) в изоляции от БД/get_material_price."""

    def test_uses_only_source_covering_requested_city(self):
        base = SimpleNamespace(covered_cities=None)
        moscow = SimpleNamespace(covered_cities=frozenset({"Москва"}))
        assert _select_regional_parsers([base, moscow], "Москва") == [moscow]

    def test_falls_back_to_uncovered_sources_when_no_source_matches_city(self):
        base = SimpleNamespace(covered_cities=None)
        moscow = SimpleNamespace(covered_cities=frozenset({"Москва"}))
        assert _select_regional_parsers([base, moscow], "Казань") == [base]

    def test_no_requested_city_falls_back_to_uncovered_sources(self):
        base = SimpleNamespace(covered_cities=None)
        moscow = SimpleNamespace(covered_cities=frozenset({"Москва"}))
        assert _select_regional_parsers([base, moscow], None) == [base]
