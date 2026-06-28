# app/tests/test_regional_prices.py
# Региональные цены с привязкой к region (#127).

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.price_aggregator_service import get_price, get_labor_price

client = TestClient(app)


# Изоляция эндпоинт-тестов от живого парсера материалов — через общую фикстуру
# stub_material_parser из conftest (#174): парсер глушится (→ seed), что делает
# проверку фактического региона детерминированной без зависимости от сети/VPN.


# --- lookup материалов ---

@pytest.mark.usefixtures("setup_test_db")
def test_material_regional_price_selected():
    """При заданном region выбирается seed-цена этого региона, а не базовая."""
    moscow = get_price("Краска для стен", region="Москва")
    base = get_price("Краска для стен", region=None)
    assert moscow is not None and base is not None
    assert moscow.region == "Москва"
    assert moscow.price_avg != base.price_avg


@pytest.mark.usefixtures("setup_test_db")
def test_material_fallback_to_seed_when_region_missing():
    """Для города без своих цен — fallback на базовую seed (region IS NULL), расчёт не падает."""
    other = get_price("Краска для стен", region="Новосибирск")
    base = get_price("Краска для стен", region=None)
    assert other is not None
    assert other.region is None
    assert other.price_avg == base.price_avg


# --- lookup работ ---

@pytest.mark.usefixtures("setup_test_db")
def test_labor_regional_price_selected():
    moscow = get_labor_price("Покраска стен", region="Москва")
    base = get_labor_price("Покраска стен", region=None)
    assert moscow is not None and base is not None
    assert moscow.region == "Москва"
    assert moscow.price_avg != base.price_avg


@pytest.mark.usefixtures("setup_test_db")
def test_labor_fallback_to_seed_when_region_missing():
    other = get_labor_price("Покраска стен", region="Новосибирск")
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


# --- сквозной расчёт: разные города дают разные суммы ---

def _payload(city: str) -> dict:
    return {
        "city": city,
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
            }
        ],
        "repair_type": "cosmetic",
        "repair_options": {
            "floor": "laminate", "walls": "paint", "ceiling": "paint",
            "electric": "basic", "plumbing": False,
        },
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
