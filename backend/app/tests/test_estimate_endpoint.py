# app/tests/test_estimate_endpoint.py

import pytest
from fastapi.testclient import TestClient
from app.main import app

# Все эндпоинт-тесты идут без сети: stub_material_parser по умолчанию глушит
# парсер материалов (→ seed). Тесты ветки «цена от парсера» переопределяют его
# вызовом stub_material_parser(fetch). См. conftest (#174).
pytestmark = pytest.mark.usefixtures("override_get_db", "stub_material_parser")

client = TestClient(app)


def test_single_room():
    payload = {
        "city": "Казань",
        "rooms": [
            {
                "name": "Спальня",
                "height": 2.7,
                "points": [
                    {"x": 0, "y": 0},
                    {"x": 4, "y": 0},
                    {"x": 4, "y": 3},
                    {"x": 0, "y": 3}
                ],
                "room_type": "living",
                "openings": [
                    {"type": "door", "width": 0.8, "height": 2.0},
                    {"type": "window", "width": 1.5, "height": 1.4}
                ]
            }
        ],
        "repair_type": "cosmetic",
        "repair_options": {
            "floor": "laminate",
            "walls": "paint",
            "ceiling": "paint",
            "electric": "basic",
            "plumbing": False
        }
    }

    response = client.post("/api/estimates/calculate", json=payload)
    assert response.status_code == 200
    data = response.json()

    # Проверка геометрии
    assert data["geometry"]["wall_area"] == pytest.approx(34.1, 0.01)
    assert data["geometry"]["floor_area"] == 12.0
    assert data["geometry"]["ceiling_area"] == 12.0
    assert data["geometry"]["perimeter"] == 14.0

    # Проверка наличия материалов и работ
    materials = data["materials"]
    assert len(materials) > 0
    paint = next((m for m in materials if m["name"] == "Краска для стен"), None)
    assert paint is not None
    assert paint["unit"] == "л"

    labor = data["labor"]
    assert len(labor) > 0
    painter = next((lab for lab in labor if lab["specialist"] == "Маляр"), None)
    assert painter is not None



def test_response_schema():
    """Проверка, что ответ соответствует схеме (нет лишних/недостающих полей)."""
    payload = {
        "city": "Казань",
        "rooms": [
            {
                "name": "Гостиная",
                "height": 3.0,
                "points": [
                    {"x": 0, "y": 0},
                    {"x": 5, "y": 0},
                    {"x": 5, "y": 4},
                    {"x": 0, "y": 4}
                ],
                "room_type": "living",
                "openings": []
            }
        ],
        "repair_type": "cosmetic",
        "repair_options": {
            "floor": "laminate",
            "walls": "paint",
            "ceiling": "paint",
            "electric": "basic",
            "plumbing": False
        }
    }
    response = client.post("/api/estimates/calculate", json=payload)
    assert response.status_code == 200
    data = response.json()

    required_summary_fields = [
        "materials_min", "materials_avg", "materials_max",
        "labor_min", "labor_avg", "labor_max",
        "total_min", "total_avg", "total_max"
    ]
    for field in required_summary_fields:
        assert field in data["summary"]

    required_geo_fields = ["floor_area", "ceiling_area", "wall_area", "perimeter"]
    for field in required_geo_fields:
        assert field in data["geometry"]

def test_single_room_exact_values():
    """Проверка точных значений для прямоугольной комнаты 4×3 с проёмами."""
    payload = {
        "city": "Казань",
        "rooms": [
            {
                "name": "Спальня",
                "height": 2.7,
                "points": [
                    {"x": 0, "y": 0},
                    {"x": 4, "y": 0},
                    {"x": 4, "y": 3},
                    {"x": 0, "y": 3}
                ],
                "room_type": "living",
                "openings": [
                    {"type": "door", "width": 0.8, "height": 2.0},
                    {"type": "window", "width": 1.5, "height": 1.4}
                ]
            }
        ],
        "repair_type": "cosmetic",
        "repair_options": {
            "floor": "laminate",
            "walls": "paint",
            "ceiling": "paint",
            "electric": "basic",
            "plumbing": False
        }
    }

    response = client.post("/api/estimates/calculate", json=payload)
    assert response.status_code == 200
    data = response.json()

    # Геометрия (с вычетом проёмов: door=0.8*2=1.6, window=1.5*1.4=2.1, всего 3.7)
    # wall_area = 14*2.7 - 3.7 = 37.8 - 3.7 = 34.1
    assert data["geometry"]["wall_area"] == pytest.approx(34.1, 0.01)
    assert data["geometry"]["floor_area"] == 12.0
    assert data["geometry"]["ceiling_area"] == 12.0
    assert data["geometry"]["perimeter"] == 14.0

    # Материалы: проверяем ламинат (округление до упаковок)
    laminate = next(m for m in data["materials"] if m["name"] == "Ламинат")
    # Площадь пола 12, запас 8% -> 12.96, package_size=2.0 -> 6.48 -> ceil -> 7 упаковок
    # Итоговое количество = 7 * 2.0 = 14.0 (в базовых единицах)
    assert laminate["quantity"] == pytest.approx(14.0, 0.01)
    # Проверим, что цена за единицу и итоговая сумма не нулевые
    assert laminate["price_avg"] > 0
    assert laminate["total_avg"] > 0

    labor = data["labor"]

    # Проверяем конкретные услуги
    paint_walls = next(item for item in labor if item["service"] == "Покраска стен")
    assert paint_walls["volume"] == pytest.approx(34.1, 0.01)

    paint_ceiling = next(item for item in labor if item["service"] == "Покраска потолка")
    assert paint_ceiling["volume"] == pytest.approx(12.0, 0.01)

    putty = next(item for item in labor if item["service"] == "Шпаклевка стен")
    assert putty["volume"] == pytest.approx(34.1, 0.01)

    # Проверяем, что есть услуги по полу и электрике (если они должны быть)
    # Например, укладка ламината
    laminate_install = next(item for item in labor if item["service"] == "Укладка ламината")
    assert laminate_install["volume"] == pytest.approx(12.0, 0.01)

    # Проверка вилки: min <= avg <= max
    summary = data["summary"]
    assert summary["materials_min"] <= summary["materials_avg"] <= summary["materials_max"]
    assert summary["labor_min"] <= summary["labor_avg"] <= summary["labor_max"]
    assert summary["total_min"] <= summary["total_avg"] <= summary["total_max"]

def test_two_rooms_grouping_and_rounding():
    """Две одинаковые комнаты: группировка материалов и удвоение с округлением."""
    room = {
        "name": "Спальня",
        "height": 2.7,
        "points": [
            {"x": 0, "y": 0},
            {"x": 4, "y": 0},
            {"x": 4, "y": 3},
            {"x": 0, "y": 3}
        ],
        "room_type": "living",
        "openings": [
            {"type": "door", "width": 0.8, "height": 2.0}
        ]
    }
    payload = {
        "city": "Казань",
        "rooms": [room, room],
        "repair_type": "cosmetic",
        "repair_options": {
            "floor": "laminate",
            "walls": "paint",
            "ceiling": "paint",
            "electric": "basic",
            "plumbing": False
        }
    }

    response = client.post("/api/estimates/calculate", json=payload)
    assert response.status_code == 200
    data = response.json()

    # Ламинат: на одну комнату 6.48 упаковок (ceil -> 7), на две комнаты 12.96 упаковок (ceil -> 13)
    # Итоговое количество = 13 * 2.0 = 26.0
    laminate = next(m for m in data["materials"] if m["name"] == "Ламинат")
    assert laminate["quantity"] == pytest.approx(26.0, 0.01)

    # Проверка, что материалы сгруппированы (должна быть одна строка ламината)
    assert len([m for m in data["materials"] if m["name"] == "Ламинат"]) == 1

    # Проверка, что итоговая сумма примерно вдвое больше, чем для одной комнаты (с учётом округления)
    # Для точности мы бы сравнили с отдельным запросом, но здесь просто проверим, что больше
    # Сделаем запрос для одной комнаты с такой же геометрией (без проёмов) и сравним
    single_room_payload = {**payload, "rooms": [room]}
    single_response = client.post("/api/estimates/calculate", json=single_room_payload)
    single_data = single_response.json()
    single_total_avg = single_data["summary"]["total_avg"]
    double_total_avg = data["summary"]["total_avg"]
    # Из-за округления double может быть не ровно в 2 раза, но должно быть больше single
    assert double_total_avg > single_total_avg


PAINT_PAYLOAD = {
    "city": "Казань",
    "rooms": [
        {
            "name": "Комната",
            "height": 2.7,
            "points": [
                {"x": 0, "y": 0}, {"x": 4, "y": 0},
                {"x": 4, "y": 3}, {"x": 0, "y": 3}
            ],
            "room_type": "living",
            "openings": []
        }
    ],
    "repair_type": "cosmetic",
    "repair_options": {
        "floor": "laminate",
        "walls": "paint",
        "ceiling": "paint",
        "electric": "basic",
        "plumbing": False
    }
}


def test_detail_totals_match_summary():
    """Сумма построчных total_avg должна совпадать с summary.*_avg (детализация бьётся с итогом)."""
    response = client.post("/api/estimates/calculate", json=PAINT_PAYLOAD)
    assert response.status_code == 200
    data = response.json()

    materials_sum = sum(m["total_avg"] for m in data["materials"])
    labor_sum = sum(lab["total_avg"] for lab in data["labor"])

    assert materials_sum == pytest.approx(data["summary"]["materials_avg"], rel=1e-6)
    assert labor_sum == pytest.approx(data["summary"]["labor_avg"], rel=1e-6)
    # И итог равен сумме материалов и работ
    assert data["summary"]["total_avg"] == pytest.approx(
        data["summary"]["materials_avg"] + data["summary"]["labor_avg"], rel=1e-6
    )


def test_parser_source_in_response(stub_material_parser):
    """Когда парсер отдаёт цену, source у краски становится 'Мегастрой', а не 'seed'."""
    from decimal import Decimal
    from app.parsers.base import ParsedPrice

    def fake_fetch(material_name):
        return ParsedPrice(
            price_min=Decimal("500"),
            price_avg=Decimal("700"),
            price_max=Decimal("900"),
        )

    stub_material_parser(fake_fetch)

    response = client.post("/api/estimates/calculate", json=PAINT_PAYLOAD)
    assert response.status_code == 200
    materials = response.json()["materials"]
    paint = next((m for m in materials if m["name"] == "Краска для стен"), None)
    assert paint is not None
    assert paint["source"] == "Мегастрой"


def test_parser_source_url_in_response(stub_material_parser):
    """Цена от парсера несёт source_url; seed-позиция отдаёт source_url = null."""
    from decimal import Decimal
    from app.parsers.base import ParsedPrice

    card_url = "https://kazan.megastroy.com/catalog/kraski-dlya-vnutrennih-rabot"

    def fake_fetch(material_name):
        # Как настоящий парсер: цена есть только для материалов из CATEGORY_MAP.
        if material_name != "Краска для стен":
            raise ValueError(f"нет категории для '{material_name}'")
        return ParsedPrice(
            price_min=Decimal("500"),
            price_avg=Decimal("700"),
            price_max=Decimal("900"),
            source_url=card_url,
        )

    stub_material_parser(fake_fetch)

    response = client.post("/api/estimates/calculate", json=PAINT_PAYLOAD)
    assert response.status_code == 200
    materials = response.json()["materials"]

    # Парсерная цена краски — ссылка ведёт на карточку.
    paint = next((m for m in materials if m["name"] == "Краска для стен"), None)
    assert paint is not None
    assert paint["source"] == "Мегастрой"
    assert paint["source_url"] == card_url

    # Ламинат парсер не знает → seed → ссылки нет.
    laminate = next((m for m in materials if m["name"] == "Ламинат"), None)
    assert laminate is not None
    assert laminate["source"] == "seed"
    assert laminate["source_url"] is None

    # Работы берутся из seed → ссылки нет.
    for lab in response.json()["labor"]:
        assert lab["source_url"] is None


def test_parser_fallback_on_error():
    """Когда парсер падает, расчёт не ломается и source остаётся 'seed'.
    Парсер по умолчанию заглушён падающим stub_material_parser → seed."""
    response = client.post("/api/estimates/calculate", json=PAINT_PAYLOAD)
    assert response.status_code == 200
    materials = response.json()["materials"]
    assert len(materials) > 0
    for m in materials:
        assert m["source"] == "seed"


def test_full_workset_has_electric_and_plumbing():
    """Санузел с полным набором: электрика и сантехника попадают в смету с объёмом > 0
    и ненулевой ценой; ни одна строка не остаётся без цены (silent P0 #181).
    Цены — из seed (парсер заглушён по умолчанию), тест не зависит от сети."""
    payload = {
        "city": "Казань",
        "rooms": [
            {
                "name": "Санузел",
                "height": 2.7,
                "points": [
                    {"x": 0, "y": 0}, {"x": 2, "y": 0},
                    {"x": 2, "y": 2}, {"x": 0, "y": 2}
                ],
                "room_type": "bathroom",
                "openings": [
                    {"type": "door", "width": 0.8, "height": 2.0}
                ]
            }
        ],
        "repair_type": "base",
        "repair_options": {
            "floor": "tile",
            "walls": "tile",
            "ceiling": "stretch",
            "electric": "extended",
            "plumbing": True
        }
    }

    response = client.post("/api/estimates/calculate", json=payload)
    assert response.status_code == 200
    data = response.json()

    labor = data["labor"]
    electric = next((x for x in labor if x["service"] == "Электромонтаж"), None)
    plumbing = next((x for x in labor if x["service"] == "Сантехнические работы"), None)

    # Объём по дефолтам room_type=bathroom: электрика extended = 5, сантехника = 3.
    assert electric is not None and electric["volume"] == pytest.approx(5.0)
    assert plumbing is not None and plumbing["volume"] == pytest.approx(3.0)
    assert electric["total_avg"] > 0 and plumbing["total_avg"] > 0
    assert electric["unit"] == "точка" and plumbing["unit"] == "точка"

    # Ни материалы, ни работы не остаются без цены на боевом наборе.
    for row in data["materials"] + data["labor"]:
        assert row["source"] != "нет цены"


def test_plinth_subtracts_door_width():
    """Плинтус считается от периметра за вычетом ширины дверей, а не по полному
    периметру (silent P0 #181). Цены — из seed (парсер заглушён по умолчанию)."""
    payload = {
        "city": "Казань",
        "rooms": [
            {
                "name": "Комната",
                "height": 2.7,
                "points": [
                    {"x": 0, "y": 0}, {"x": 4, "y": 0},
                    {"x": 4, "y": 3}, {"x": 0, "y": 3}
                ],
                "room_type": "living",
                "openings": [
                    {"type": "door", "width": 0.8, "height": 2.0}
                ]
            }
        ],
        "repair_type": "cosmetic",
        "repair_options": {
            "floor": "laminate",
            "walls": "paint",
            "ceiling": "paint",
            "electric": "basic",
            "plumbing": False
        }
    }

    response = client.post("/api/estimates/calculate", json=payload)
    assert response.status_code == 200
    plinth = next(m for m in response.json()["materials"] if m["name"] == "Плинтус")

    # Периметр 14, дверь 0.8, waste 1.05, package_size 1.0:
    # (14 − 0.8) × 1.05 = 13.86 → ceil = 14 пог.м (с дверью).
    # Без вычета двери было бы 14 × 1.05 = 14.7 → ceil = 15.
    assert plinth["quantity"] == pytest.approx(14.0)
