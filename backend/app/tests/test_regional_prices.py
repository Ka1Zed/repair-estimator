# app/tests/test_regional_prices.py
# Региональные цены с привязкой к region (#127).

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.api.estimates import get_material_parsers
from app.parsers.base import BaseParser, ParsedPrice
from app.services.price_aggregator_service import get_price, get_labor_price

client = TestClient(app)


# Изоляция эндпоинт-тестов от живого парсера материалов — через общую фикстуру
# stub_material_parser из conftest (#174): парсер глушится (→ seed), что делает
# проверку фактического региона детерминированной без зависимости от сети/VPN.


# --- lookup материалов ---

def test_material_regional_price_selected(db_session):
    """При заданном region выбирается seed-цена этого региона, а не базовая."""
    moscow = get_price("Краска для стен", db=db_session, region="Москва")
    base = get_price("Краска для стен", db=db_session, region=None)
    assert moscow is not None and base is not None
    assert moscow.region == "Москва"
    assert moscow.price_avg != base.price_avg


def test_material_fallback_to_seed_when_region_missing(db_session):
    """Для города без своих цен — fallback на базовую seed (region IS NULL), расчёт не падает."""
    other = get_price("Краска для стен", db=db_session, region="Новосибирск")
    base = get_price("Краска для стен", db=db_session, region=None)
    assert other is not None
    assert other.region is None
    assert other.price_avg == base.price_avg


# --- lookup работ ---

def test_labor_regional_price_selected(db_session):
    moscow = get_labor_price("Покраска стен", db=db_session, region="Москва")
    base = get_labor_price("Покраска стен", db=db_session, region=None)
    assert moscow is not None and base is not None
    assert moscow.region == "Москва"
    assert moscow.price_avg != base.price_avg


def test_labor_fallback_to_seed_when_region_missing(db_session):
    other = get_labor_price("Покраска стен", db=db_session, region="Новосибирск")
    assert other is not None
    assert other.region is None


# --- справочник регионов ---

@pytest.mark.usefixtures("override_get_db")
def test_regions_endpoint():
    response = client.get("/api/regions")
    assert response.status_code == 200
    body = response.json()
    assert body["default"] == "Казань"
    assert "Москва" in body["regions"]
    # Город по умолчанию всегда присутствует в списке.
    assert "Казань" in body["regions"]


# --- справочник магазинов по городу (#363) ---

def test_stores_endpoint_kazan_both_available():
    """Казань не покрыта ни одним региональным источником (covered_cities) →
    оба зарегистрированных магазина (Мегастрой, базовый Леман) доступны."""
    response = client.get("/api/regions/stores", params={"city": "Казань"})
    assert response.status_code == 200
    body = response.json()
    assert body["city"] == "Казань"
    stores = {s["name"]: s["available"] for s in body["stores"]}
    assert stores == {"Мегастрой": True, "Леман": True}


def test_stores_endpoint_moscow_megastroy_unavailable():
    """Москва покрыта региональным Леман-Москва (covered_cities={'Москва'}) →
    он подменяет безрегиональные источники: Мегастрой недоступен физически."""
    response = client.get("/api/regions/stores", params={"city": "Москва"})
    assert response.status_code == 200
    body = response.json()
    stores = {s["name"]: s["available"] for s in body["stores"]}
    assert stores == {"Мегастрой": False, "Леман": True}


# --- сквозной расчёт: разные города дают разные суммы ---

def _payload(city: str, stores: list[str] | None = None) -> dict:
    return {
        "city": city,
        **({"stores": stores} if stores is not None else {}),
        "rooms": [
            {
                "name": "Комната",
                "height": 2.7,
                "points": [
                    {"x": 0, "y": 0}, {"x": 4, "y": 0},
                    {"x": 4, "y": 3}, {"x": 0, "y": 3},
                ],
                "room_type": "living",
                "openings": [],
                "works": {
                    "floor": {"enabled": True, "finish": "laminate"},
                    "walls": {"enabled": True, "finish": "paint"},
                    "ceiling": {"enabled": True, "finish": "paint"},
                    "electric": {"enabled": True},
                    "plumbing": {"enabled": False},
                },
            }
        ],
    }


@pytest.mark.usefixtures("override_get_db", "stub_material_parser")
def test_estimate_labor_differs_by_city():
    """Покраска стен в Москве дороже базовой → labor_avg для Москвы выше, чем для города без цен."""
    moscow = client.post("/api/estimates/calculate", json=_payload("Москва")).json()
    other = client.post("/api/estimates/calculate", json=_payload("Тверь")).json()
    assert moscow["summary"]["labor_avg"] != other["summary"]["labor_avg"]


@pytest.mark.usefixtures("override_get_db", "stub_material_parser")
def test_estimate_item_reports_actual_region():
    """Строка ответа несёт фактический регион цены: город при региональной seed,
    null при fallback на базовую — а не просто эхо запрошенного city.
    Парсер материалов заглушён (stub_material_parser), цены берутся из seed."""
    moscow = client.post("/api/estimates/calculate", json=_payload("Москва")).json()
    other = client.post("/api/estimates/calculate", json=_payload("Тверь")).json()

    paint_msk = next(m for m in moscow["materials"] if m["name"] == "Краска для стен")
    paint_other = next(m for m in other["materials"] if m["name"] == "Краска для стен")

    assert paint_msk["region"] == "Москва"
    # Для города без своих цен сработал fallback на базовую → region == null, а не "Тверь".
    assert paint_other["region"] is None


# --- сквозной выбор регионального источника материалов (#345) ---
# Проверяем проводку эндпоинта целиком: get_material_parsers отдаёт региональные
# парсеры, а get_material_price/_select_regional_parsers исключает безрегиональный
# Мегастрой для города с выделенным источником (Леман-Москва) и объединяет оба
# источника для города без такого (Казань). Юнит-уровень покрыт в
# test_price_normalization.py — здесь то же поведение, но через реальный
# /api/estimates, а не только в сервисе.


class _StubRegionalParser(BaseParser):
    """Локальная заглушка парсера материалов: отдаёт фиксированную parser-цену,
    в сеть не ходит. Параметризуется source_name/region/covered_cities под
    конкретный сценарий (мимикрия под MATERIAL_PARSERS + REGIONAL_MATERIAL_PARSERS)."""

    def __init__(self, source_name, avg, *, region=None, covered_cities=None):
        self.source_name = source_name
        self.region = region
        self.covered_cities = covered_cities
        self._avg = Decimal(avg)

    def fetch_price(self, material_name: str, reference_package_size=None) -> ParsedPrice:
        return ParsedPrice(
            price_min=self._avg - 20,
            price_avg=self._avg,
            price_max=self._avg + 20,
            source_url=f"https://example/{self.source_name}",
        )


@pytest.fixture
def regional_material_parsers(override_get_db):
    """get_material_parsers → Мегастрой (без региона) + базовый Леман (Казань,
    без региона) + Леман-Москва (covered_cities={'Москва'}) — как в реальном
    registry. Чистит осевшие parser-цены до и после, чтобы TTL-кэш не протекал
    между тестами (общая тест-БД)."""
    from app.tests.conftest import _clear_parser_material_prices

    _clear_parser_material_prices()
    app.dependency_overrides[get_material_parsers] = lambda: [
        _StubRegionalParser("Мегастрой", "100"),
        _StubRegionalParser("Леман", "300"),
        _StubRegionalParser("Леман", "250", region="Москва", covered_cities=frozenset({"Москва"})),
    ]
    yield
    app.dependency_overrides.pop(get_material_parsers, None)
    _clear_parser_material_prices()


def test_moscow_estimate_uses_only_regional_leman(regional_material_parsers):
    """Москва: в вилку идёт только Леман-Москва; Мегастрой (физически вне Москвы,
    без covered_cities) и базовый Леман-Казань исключены, region строки == 'Москва'."""
    body = client.post("/api/estimates/calculate", json=_payload("Москва")).json()
    paint = next(m for m in body["materials"] if m["name"] == "Краска для стен")

    assert paint["sources"] == ["Леман"]
    assert paint["region"] == "Москва"
    assert paint["price_avg"] == 250.0


def test_kazan_estimate_combines_default_sources(regional_material_parsers):
    """Казань: covered_cities ни у кого не совпал → участвуют оба безрегиональных
    источника (Мегастрой + базовый Леман), региональный Леман-Москва не подмешан,
    region строки == null (как раньше)."""
    body = client.post("/api/estimates/calculate", json=_payload("Казань")).json()
    paint = next(m for m in body["materials"] if m["name"] == "Краска для стен")

    assert set(paint["sources"]) == {"Мегастрой", "Леман"}
    assert paint["region"] is None


def test_moscow_estimate_consistent_source_across_finish_key_materials(regional_material_parsers):
    """Регресс issue #347: несколько finish_key-позиций одного расчёта (ламинат,
    покраска стен, покраска потолка — все резолвятся через _resolve_material/tier,
    #331) должны получать источник консистентно — все региональный Леман-Москва,
    без разнобоя с Мегастроем на однотипных позициях одного и того же города.

    Живой прогон, зафиксировавший issue, оказался против несобранного после #345
    Docker-образа backend (см. обсуждение issue) — здесь тот же сценарий закреплён
    тестом на актуальном коде, чтобы регрессия не могла пройти незамеченной."""
    body = client.post("/api/estimates/calculate", json=_payload("Москва")).json()
    finish_names = {"Ламинат", "Краска для стен", "Краска потолочная"}
    finish_items = [m for m in body["materials"] if m["name"] in finish_names]

    assert {m["name"] for m in finish_items} == finish_names
    assert all(m["sources"] == ["Леман"] for m in finish_items)
    assert all(m["region"] == "Москва" for m in finish_items)


def test_kazan_estimate_consistent_source_across_finish_key_materials(regional_material_parsers):
    """Симметрия #347 для города без выделенного источника: те же finish_key-позиции
    в Казани консистентно берут оба безрегиональных источника (Мегастрой + базовый
    Леман), региональный Леман-Москва не подмешивается ни к одной, region == null."""
    body = client.post("/api/estimates/calculate", json=_payload("Казань")).json()
    finish_names = {"Ламинат", "Краска для стен", "Краска потолочная"}
    finish_items = [m for m in body["materials"] if m["name"] in finish_names]

    assert {m["name"] for m in finish_items} == finish_names
    assert all(set(m["sources"]) == {"Мегастрой", "Леман"} for m in finish_items)
    assert all(m["region"] is None for m in finish_items)


# --- явный выбор магазина в /calculate (#363) ---

def test_kazan_estimate_narrows_to_selected_store(regional_material_parsers):
    """Казань: оба безрегиональных источника покрывают город, но пользователь явно
    выбрал только Леман → в вилку идёт только он, Мегастрой не подмешивается."""
    body = client.post(
        "/api/estimates/calculate", json=_payload("Казань", stores=["Леман"])
    ).json()
    paint = next(m for m in body["materials"] if m["name"] == "Краска для стен")

    assert paint["sources"] == ["Леман"]
    assert paint["price_avg"] == 300.0


def test_moscow_estimate_falls_back_when_selected_store_unavailable(regional_material_parsers):
    """Москва: пользователь выбрал Мегастрой, но он физически не покрывает город
    (единственный источник — региональный Леман-Москва) → тихий откат на
    авто-подбор, а не пустая цена/падение."""
    with_store = client.post(
        "/api/estimates/calculate", json=_payload("Москва", stores=["Мегастрой"])
    ).json()
    without_store = client.post(
        "/api/estimates/calculate", json=_payload("Москва")
    ).json()

    paint_with = next(m for m in with_store["materials"] if m["name"] == "Краска для стен")
    paint_without = next(m for m in without_store["materials"] if m["name"] == "Краска для стен")

    assert paint_with["sources"] == ["Леман"]
    assert paint_with["price_avg"] == paint_without["price_avg"] == 250.0


def test_estimate_rejects_unknown_store_name(regional_material_parsers):
    """Опечатка в имени магазина — не то же самое, что «магазин не покрывает
    город»: должна вернуться явная 422, а не тихий откат на автоподбор."""
    response = client.post(
        "/api/estimates/calculate", json=_payload("Казань", stores=["Ленман"])
    )
    assert response.status_code == 422
    assert "Ленман" in response.json()["detail"]
