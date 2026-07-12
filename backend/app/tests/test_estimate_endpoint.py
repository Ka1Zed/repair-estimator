# app/tests/test_estimate_endpoint.py

import pytest
from fastapi.testclient import TestClient
from app.main import app

# Все эндпоинт-тесты идут без сети: stub_material_parser по умолчанию глушит
# парсер материалов (→ seed). Тесты ветки «цена от парсера» переопределяют его
# вызовом stub_material_parser(fetch). См. conftest (#174).
pytestmark = pytest.mark.usefixtures("override_get_db", "stub_material_parser")

client = TestClient(app)


def W(floor="laminate", walls="paint", ceiling="paint", electric=True, plumbing=False):
    """Блок works для комнаты. finish=None → поверхность выключена."""
    return {
        "floor": {"enabled": floor is not None, "finish": floor},
        "walls": {"enabled": walls is not None, "finish": walls},
        "ceiling": {"enabled": ceiling is not None, "finish": ceiling},
        "electric": {"enabled": electric},
        "plumbing": {"enabled": plumbing},
    }


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
                ],
                "works": W()
            }
        ]
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
                "openings": [],
                "works": W()
            }
        ]
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

    # Детализация строки материала (#176): состав quantity должен быть виден фронту.
    required_material_fields = ["base_quantity", "waste_factor", "package_size", "packs"]
    assert len(data["materials"]) > 0
    for material in data["materials"]:
        for field in required_material_fields:
            assert field in material


def test_no_repair_type_required():
    """Класса ремонта в контракте больше нет: запрос без repair_type успешно считается (#222)."""
    payload = {
        "city": "Казань",
        "rooms": [
            {
                "name": "Спальня",
                "height": 2.7,
                "points": [
                    {"x": 0, "y": 0}, {"x": 4, "y": 0},
                    {"x": 4, "y": 3}, {"x": 0, "y": 3}
                ],
                "room_type": "living",
                "openings": [],
                "works": W(),
            }
        ]
    }
    response = client.post("/api/estimates/calculate", json=payload)
    assert response.status_code == 200


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
                ],
                "works": W()
            }
        ]
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
    # Площадь пола 12, запас 15% -> 13.8, package_size=2.0 -> 6.9 -> ceil -> 7 упаковок
    # Итоговое количество = 7 * 2.0 = 14.0 (в базовых единицах)
    assert laminate["quantity"] == pytest.approx(14.0, 0.01)
    # Детализация строки (#176): base_quantity (до запаса) * waste_factor округляется
    # вверх до package_size и даёт итоговый quantity.
    assert laminate["base_quantity"] == pytest.approx(12.0, 0.01)
    assert laminate["waste_factor"] == pytest.approx(1.15, 0.01)
    assert laminate["package_size"] == pytest.approx(2.0, 0.01)
    assert laminate["packs"] == 7
    assert laminate["quantity"] == pytest.approx(laminate["packs"] * laminate["package_size"], 0.001)
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

    # Например, укладка ламината
    laminate_install = next(item for item in labor if item["service"] == "Укладка ламината")
    assert laminate_install["volume"] == pytest.approx(12.0, 0.01)

    # Проверка вилки: min <= avg <= max
    summary = data["summary"]
    assert summary["materials_min"] <= summary["materials_avg"] <= summary["materials_max"]
    assert summary["labor_min"] <= summary["labor_avg"] <= summary["labor_max"]
    assert summary["total_min"] <= summary["total_avg"] <= summary["total_max"]


def test_no_class_multiplier():
    """Класс ремонта убран: итог = материалы + работы, без классового множителя (#222).
    Каждый агрегат = сумма строк × непредвиденные (CONTINGENCY)."""
    response = client.post("/api/estimates/calculate", json=PAINT_PAYLOAD)
    assert response.status_code == 200
    summary = response.json()["summary"]

    # avg-запас = 1.12 (CONTINGENCY). total_avg = (materials_avg + labor_avg), без ×коэфф. класса.
    assert summary["total_avg"] == pytest.approx(
        summary["materials_avg"] + summary["labor_avg"], rel=1e-6
    )


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
        ],
        "works": W()
    }
    payload = {"city": "Казань", "rooms": [room, room]}

    response = client.post("/api/estimates/calculate", json=payload)
    assert response.status_code == 200
    data = response.json()

    # Ламинат: на одну комнату 6.9 упаковок (ceil -> 7), на две комнаты 13.8 упаковок (ceil -> 14)
    # Итоговое количество = 14 * 2.0 = 28.0
    laminate = next(m for m in data["materials"] if m["name"] == "Ламинат")
    assert laminate["quantity"] == pytest.approx(28.0, 0.01)

    # Проверка, что материалы сгруппированы (должна быть одна строка ламината)
    assert len([m for m in data["materials"] if m["name"] == "Ламинат"]) == 1

    # Двойной набор должен быть дороже одиночного (с учётом округления).
    single_response = client.post("/api/estimates/calculate", json={**payload, "rooms": [room]})
    single_total_avg = single_response.json()["summary"]["total_avg"]
    double_total_avg = data["summary"]["total_avg"]
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
            "openings": [],
            "works": W()
        }
    ]
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


def test_parser_package_size_overrides_static_and_stays_consistent_with_quantity(stub_material_parser):
    """package_size (#306): парсер отдал фасовку КОНКРЕТНОГО товара (2.5 л) —
    отличную от статичной Material.package_size (9 л, см. conftest). В ответе
    package_size должен быть от парсера, а не статика, и инвариант из api.md
    (quantity == packs × package_size) обязан сойтись — иначе source_url на
    странице (product за 2.5 л) и число упаковок в смете снова разъедутся."""
    from decimal import Decimal
    from app.parsers.base import ParsedPrice

    card_url = "https://kazan.megastroy.com/products/kraska-2.5l"

    def fake_fetch(material_name):
        if material_name != "Краска для стен":
            raise ValueError(f"нет категории для '{material_name}'")
        return ParsedPrice(
            price_min=Decimal("500"),
            price_avg=Decimal("700"),
            price_max=Decimal("900"),
            source_url=card_url,
            package_size=Decimal("2.5"),
        )

    stub_material_parser(fake_fetch)

    response = client.post("/api/estimates/calculate", json=PAINT_PAYLOAD)
    assert response.status_code == 200
    materials = response.json()["materials"]
    paint = next((m for m in materials if m["name"] == "Краска для стен"), None)

    assert paint is not None
    assert paint["source_url"] == card_url
    assert paint["package_size"] == pytest.approx(2.5)
    assert paint["package_size"] != 9  # не статика из materials.json
    assert paint["quantity"] == pytest.approx(paint["packs"] * paint["package_size"], rel=1e-6)


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
    """Санузел с полным набором: электрика и сантехника попадают в смету по дефолтам
    (числа не заданы) с объёмом > 0 и ненулевой ценой; ни одна строка не без цены (#181).
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
                ],
                "works": W(floor="tile", walls="tile", ceiling="stretch",
                           electric=True, plumbing=True)
            }
        ]
    }

    response = client.post("/api/estimates/calculate", json=payload)
    assert response.status_code == 200
    data = response.json()

    labor = {x["service"]: x for x in data["labor"]}

    # Дефолты bathroom: розетки 4, светильники 2 → кабель (4+2)*6 = 36 м.
    assert labor["Монтаж розетки"]["volume"] == pytest.approx(4.0)
    assert labor["Монтаж розетки"]["unit"] == "шт"
    assert labor["Монтаж светильника"]["volume"] == pytest.approx(2.0)
    assert labor["Прокладка кабеля"]["volume"] == pytest.approx(36.0)
    assert labor["Прокладка кабеля"]["unit"] == "м"

    # Сантехника bathroom по дефолту: 3 точки → труба 3*3 = 9 м.
    assert labor["Сантехнические работы"]["volume"] == pytest.approx(3.0)
    assert labor["Сантехнические работы"]["unit"] == "точка"
    assert labor["Монтаж труб"]["volume"] == pytest.approx(9.0)

    for name in ("Монтаж розетки", "Прокладка кабеля", "Сантехнические работы", "Монтаж труб"):
        assert labor[name]["total_avg"] > 0

    # Материалы инженерки: розетки/светильники штучно, кабель/труба с запасом.
    mats = {m["name"]: m for m in data["materials"]}
    assert mats["Розетка"]["quantity"] == pytest.approx(4.0)
    assert mats["Светильник"]["quantity"] == pytest.approx(2.0)

    # Ни материалы, ни работы не остаются без цены на боевом наборе.
    for row in data["materials"] + data["labor"]:
        assert row["source"] != "нет цены"


def test_price_source_id_lookup_is_not_n_plus_one():
    """Раньше estimates.py резолвил имя источника через db.query(PriceSource)
    .filter(PriceSource.id == ...) на каждую строку материала/работы (N+1, #278).
    Теперь источники грузятся один раз словарём — SQL с фильтром по
    price_sources.id в запросе быть не должно вовсе (независимо от того, сколько
    разных материалов/работ в смете)."""
    import re

    import sqlalchemy as sa

    from app.db.session import engine

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
                ],
                "works": W(floor="tile", walls="tile", ceiling="stretch",
                           electric=True, plumbing=True)
            }
        ]
    }

    statements = []

    def _capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    sa.event.listen(engine, "before_cursor_execute", _capture)
    try:
        response = client.post("/api/estimates/calculate", json=payload)
    finally:
        sa.event.remove(engine, "before_cursor_execute", _capture)

    assert response.status_code == 200

    id_lookup_re = re.compile(r"price_sources\.id\s*=", re.IGNORECASE)
    id_lookups = [s for s in statements if id_lookup_re.search(s)]
    assert id_lookups == [], (
        f"найден точечный запрос PriceSource по id (N+1): {id_lookups}"
    )

    # Ровно один запрос грузит весь справочник источников (без WHERE по id).
    preload = [s for s in statements if "FROM price_sources" in s and "WHERE" not in s]
    assert len(preload) == 1


def test_explicit_zero_disables_default():
    """Явный 0 в числовом поле — осознанный ноль: дефолт не подставляется (#222)."""
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
                "openings": [{"type": "door", "width": 0.8, "height": 2.0}],
                "works": {
                    "floor": {"enabled": True, "finish": "tile"},
                    "walls": {"enabled": True, "finish": "tile"},
                    "ceiling": {"enabled": False, "finish": None},
                    "electric": {"enabled": False},
                    # Сантехника включена, но точек и труб — явный 0.
                    "plumbing": {"enabled": True, "points": 0, "pipe_m": 0},
                }
            }
        ]
    }
    response = client.post("/api/estimates/calculate", json=payload)
    assert response.status_code == 200
    services = {x["service"] for x in response.json()["labor"]}
    # Явный 0 → сантехнических работ и монтажа труб нет.
    assert "Сантехнические работы" not in services
    assert "Монтаж труб" not in services


def test_plumbing_enabled_adds_plumbing_rows():
    """works.plumbing.enabled=true (числа не заданы) → в ответе появляются строки сантехники."""
    payload = {
        "city": "Казань",
        "rooms": [
            {
                "name": "Кухня",
                "height": 2.7,
                "points": [
                    {"x": 0, "y": 0}, {"x": 3, "y": 0},
                    {"x": 3, "y": 3}, {"x": 0, "y": 3}
                ],
                "room_type": "kitchen",
                "openings": [],
                "works": W(floor="laminate", walls="paint", ceiling="paint",
                           electric=False, plumbing=True)
            }
        ]
    }
    response = client.post("/api/estimates/calculate", json=payload)
    assert response.status_code == 200
    services = {x["service"] for x in response.json()["labor"]}
    assert "Сантехнические работы" in services


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
                ],
                "works": W()
            }
        ]
    }

    response = client.post("/api/estimates/calculate", json=payload)
    assert response.status_code == 200
    plinth = next(m for m in response.json()["materials"] if m["name"] == "Плинтус")

    # Периметр 14, дверь 0.8, waste 1.05, package_size 1.0:
    # (14 − 0.8) × 1.05 = 13.86 → ceil = 14 пог.м (с дверью).
    # Без вычета двери было бы 14 × 1.05 = 14.7 → ceil = 15.
    assert plinth["quantity"] == pytest.approx(14.0)


def _bathroom_payload(scope=None):
    """Санузел с плиткой; scope=None → поле не отправляем (проверяем дефолт)."""
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
                "openings": [{"type": "door", "width": 0.8, "height": 2.0}],
                "works": W(floor="tile", walls="tile", ceiling=None,
                           electric=True, plumbing=True),
            }
        ],
    }
    if scope is not None:
        payload["scope"] = scope
    return payload


def test_finish_only_is_default_and_labeled():
    """Дефолт scope=finish_only: черновых работ нет, ответ явно помечен финишным (#190)."""
    response = client.post("/api/estimates/calculate", json=_bathroom_payload())
    assert response.status_code == 200
    data = response.json()

    # Ответ явно сообщает, что это только финиш (фронт не выдаст его за полную смету).
    assert data["scope"] == "finish_only"

    services = {x["service"] for x in data["labor"]}
    for rough in ("Демонтаж", "Выравнивание стен", "Стяжка пола", "Гидроизоляция", "Грунтование"):
        assert rough not in services
    # У каждой строки работ есть стадия.
    assert all("stage" in lab for lab in data["labor"])


def test_finish_only_keeps_engineering_wiring():
    """scope=finish_only + электрика/сантехника включены: разводка (Прокладка кабеля,
    Монтаж труб, stage=rough) остаётся — она не входит в «жёсткие связки», которыми
    управляет scope (#304). Монтаж приборов (finish) при этом тоже присутствует —
    в finish_only чистовая отделка не исключается, исключаются только черновые."""
    response = client.post("/api/estimates/calculate", json=_bathroom_payload())
    assert response.status_code == 200
    data = response.json()
    assert data["scope"] == "finish_only"

    labor = {x["service"]: x for x in data["labor"]}
    for wiring in ("Прокладка кабеля", "Монтаж труб"):
        assert wiring in labor, f"разводка «{wiring}» должна остаться в finish_only"
        assert labor[wiring]["stage"] == "rough"
        assert labor[wiring]["total_avg"] > 0

    for fixture in ("Монтаж розетки", "Монтаж светильника", "Сантехнические работы"):
        assert fixture in labor, f"монтаж приборов «{fixture}» должен остаться в finish_only"
        assert labor[fixture]["stage"] == "finish"

    for rough in ("Демонтаж", "Выравнивание стен", "Стяжка пола", "Гидроизоляция", "Грунтование"):
        assert rough not in labor, f"черновая работа «{rough}» не должна попасть в finish_only"


def test_rough_scope_adds_rough_works():
    """scope=rough_and_finish: черновые работы санузла попадают в смету со стадией rough (#190)."""
    response = client.post("/api/estimates/calculate",
                           json=_bathroom_payload("rough_and_finish"))
    assert response.status_code == 200
    data = response.json()
    assert data["scope"] == "rough_and_finish"

    labor = {x["service"]: x for x in data["labor"]}
    for rough in ("Демонтаж", "Выравнивание стен", "Стяжка пола", "Гидроизоляция", "Грунтование"):
        assert rough in labor, f"нет черновой работы «{rough}»"
        assert labor[rough]["stage"] == "rough"
        assert labor[rough]["total_avg"] > 0

    # Гидроизоляция санузла обязательна и считается по площади пола (4 м²).
    assert labor["Гидроизоляция"]["volume"] == pytest.approx(4.0)


def test_rough_only_excludes_finish_labor():
    """scope=rough_only: черновая+предчистовая есть, чистовой отделки нет (#303)."""
    response = client.post("/api/estimates/calculate",
                           json={**PAINT_PAYLOAD, "scope": "rough_only"})
    assert response.status_code == 200
    data = response.json()
    assert data["scope"] == "rough_only"

    labor = {x["service"]: x for x in data["labor"]}
    for rough in ("Демонтаж", "Выравнивание стен", "Стяжка пола", "Грунтование",
                  "Прокладка кабеля"):
        assert rough in labor, f"нет черновой работы «{rough}»"
        assert labor[rough]["stage"] == "rough"

    # Шпаклёвка стен (предчистовая) не входит в жёсткие связки scope — остаётся всегда.
    assert "Шпаклевка стен" in labor
    assert labor["Шпаклевка стен"]["stage"] == "pre_finish"

    for finish in ("Покраска стен", "Покраска потолка", "Укладка ламината",
                   "Монтаж розетки", "Монтаж светильника"):
        assert finish not in labor, f"чистовая работа «{finish}» не должна попасть в rough_only"

    assert all(x["stage"] != "finish" for x in data["labor"])


def test_rough_only_excludes_finish_materials():
    """scope=rough_only: остаются грунт/стартовая шпаклёвка, чистовых материалов нет (#303)."""
    response = client.post("/api/estimates/calculate",
                           json={**PAINT_PAYLOAD, "scope": "rough_only"})
    assert response.status_code == 200
    data = response.json()

    names = {m["name"] for m in data["materials"]}
    assert {"Грунтовка", "Шпаклевка стартовая"} <= names
    # Разводка (кабель) — черновой этап, материал остаётся; приборы (розетка/светильник) —
    # чистовые, их монтажа в rough_only нет, значит и закупки быть не должно (#303).
    assert "Кабель электрический" in names
    for finish in ("Ламинат", "Краска для стен", "Краска потолочная", "Плинтус",
                   "Шпаклевка финишная", "Розетка", "Светильник"):
        assert finish not in names, f"чистовой материал «{finish}» не должен попасть в rough_only"


def test_rough_only_bathroom_keeps_waterproof_no_tile():
    """scope=rough_only в мокрой зоне: гидроизоляция есть, плитка/клей/затирка — нет (#303)."""
    response = client.post("/api/estimates/calculate",
                           json=_bathroom_payload("rough_only"))
    assert response.status_code == 200
    data = response.json()

    labor = {x["service"]: x for x in data["labor"]}
    assert "Гидроизоляция" in labor
    assert labor["Гидроизоляция"]["stage"] == "rough"
    assert "Укладка плитки" not in labor

    names = {m["name"] for m in data["materials"]}
    assert not ({"Плитка", "Плиточный клей", "Затирка"} & names)


WALLPAPER_PAYLOAD = {
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
            "openings": [],
            "works": W(walls="wallpaper")
        }
    ]
}


def test_wallpaper_adds_wall_prep_materials():
    """walls=wallpaper: под обои считаются грунт и стартовая шпаклёвка, финишная — нет (#325)."""
    response = client.post("/api/estimates/calculate", json=WALLPAPER_PAYLOAD)
    assert response.status_code == 200
    data = response.json()
    assert data["scope"] == "finish_only"

    materials = {m["name"]: m for m in data["materials"]}
    for name in ("Грунтовка", "Шпаклевка стартовая", "Обои"):
        assert name in materials, f"нет материала «{name}» под обои"

    # Финишная шпаклёвка под обои избыточна — полотно скрывает огрехи (#325).
    assert "Шпаклевка финишная" not in materials

    # wall_area = (4+3)*2*2.7 = 37.8 (проёмов нет)
    wall_area = data["geometry"]["wall_area"]
    assert wall_area == pytest.approx(37.8, 0.01)

    primer = materials["Грунтовка"]
    assert primer["base_quantity"] == pytest.approx(wall_area * 0.12, rel=0.01)

    putty_start = materials["Шпаклевка стартовая"]
    assert putty_start["base_quantity"] == pytest.approx(wall_area * 5.0, rel=0.01)


def test_wallpaper_rough_only_keeps_prep_drops_wallpaper():
    """scope=rough_only под обои: грунт/стартовая шпаклёвка остаются, сами обои — нет (#325)."""
    response = client.post("/api/estimates/calculate",
                           json={**WALLPAPER_PAYLOAD, "scope": "rough_only"})
    assert response.status_code == 200
    data = response.json()

    names = {m["name"] for m in data["materials"]}
    assert {"Грунтовка", "Шпаклевка стартовая"} <= names
    assert "Обои" not in names


def test_hidden_works_block_present_and_not_in_summary():
    """Блок скрытых работ есть, помечен, но НЕ влияет на summary основной сметы (#239)."""
    response = client.post("/api/estimates/calculate", json=PAINT_PAYLOAD)
    assert response.status_code == 200
    data = response.json()

    hidden = data["hidden_works"]
    assert hidden["note"]  # явная пометка «может всплыть доплатой»
    services = {x["service"] for x in hidden["items"]}
    # Жилая комната с отделкой пола/стен и электрикой: демонтаж всегда, плюс стяжка,
    # выравнивание стен, штробы под кабель. Гидроизоляции в сухой комнате нет.
    assert {"Демонтаж", "Стяжка пола", "Выравнивание стен", "Штробление"} <= services
    assert "Гидроизоляция" not in services
    assert hidden["total_avg"] > 0

    for item in hidden["items"]:
        assert item["reason"]
        assert item["total_min"] <= item["total_avg"] <= item["total_max"]

    # Ключевой инвариант: суммы блока не попадают в summary. Сумма строк labor[]
    # (где скрытых работ нет) по-прежнему равна summary.labor_avg.
    labor_sum = sum(lab["total_avg"] for lab in data["labor"])
    assert labor_sum == pytest.approx(data["summary"]["labor_avg"], rel=1e-6)
    hidden_services = {x["service"] for x in hidden["items"]}
    assert hidden_services.isdisjoint({lab["service"] for lab in data["labor"]})


def test_hidden_works_scenario_driven():
    """Гидроизоляция всплывает только в мокрой зоне; штробы — при электрике (#239)."""
    bath = client.post("/api/estimates/calculate", json=_bathroom_payload()).json()
    bath_services = {x["service"] for x in bath["hidden_works"]["items"]}
    assert "Гидроизоляция" in bath_services

    hidden = bath["hidden_works"]["items"]
    waterproof = next(x for x in hidden if x["service"] == "Гидроизоляция")
    # Санузел 2×2 → площадь пола 4 м², объём гидроизоляции по полу.
    assert waterproof["volume"] == pytest.approx(4.0)


def test_hidden_works_waterproof_only_wet_floor():
    """Гидроизоляция считается по площади пола мокрых комнат, а не по общей (#239).

    Квартира: жилая 4×3=12 м² (сухая) + санузел 2×2=4 м² (мокрая). Гидроизоляция
    должна идти только по 4 м² санузла, а не по 16 м² всего пола.
    """
    payload = {
        "city": "Казань",
        "rooms": [
            {
                "name": "Комната", "height": 2.7,
                "points": [{"x": 0, "y": 0}, {"x": 4, "y": 0},
                           {"x": 4, "y": 3}, {"x": 0, "y": 3}],
                "room_type": "living", "openings": [], "works": W(),
            },
            {
                "name": "Санузел", "height": 2.7,
                "points": [{"x": 0, "y": 0}, {"x": 2, "y": 0},
                           {"x": 2, "y": 2}, {"x": 0, "y": 2}],
                "room_type": "bathroom",
                "openings": [{"type": "door", "width": 0.8, "height": 2.0}],
                "works": W(floor="tile", walls="tile", ceiling=None,
                           electric=True, plumbing=True),
            },
        ],
    }
    data = client.post("/api/estimates/calculate", json=payload).json()
    items = data["hidden_works"]["items"]
    waterproof = next(x for x in items if x["service"] == "Гидроизоляция")
    assert waterproof["volume"] == pytest.approx(4.0)  # только санузел, не 16


def test_hidden_works_independent_of_scope():
    """Блок скрытых работ одинаков при всех трёх scope (#239, #303).

    Скрытые работы — риск неизвестного основания, ортогональный глубине сметы:
    в summary они не входят ни при каком scope, состав от scope не зависит.
    """
    finish = client.post("/api/estimates/calculate",
                         json=_bathroom_payload("finish_only")).json()
    rough = client.post("/api/estimates/calculate",
                        json=_bathroom_payload("rough_and_finish")).json()
    rough_only = client.post("/api/estimates/calculate",
                             json=_bathroom_payload("rough_only")).json()

    def services(d):
        return {x["service"] for x in d["hidden_works"]["items"]}

    assert services(finish) == services(rough) == services(rough_only)
    assert finish["hidden_works"]["total_avg"] == pytest.approx(
        rough["hidden_works"]["total_avg"])
    assert finish["hidden_works"]["total_avg"] == pytest.approx(
        rough_only["hidden_works"]["total_avg"])


def test_invalid_scope_rejected():
    """rough_only — валидный scope; неизвестная строка отклоняется (422)."""
    response = client.post("/api/estimates/calculate",
                           json=_bathroom_payload("rough_only"))
    assert response.status_code == 200

    response = client.post("/api/estimates/calculate",
                           json=_bathroom_payload("only_rough"))
    assert response.status_code == 422


def test_invalid_door_height():
    """Дверь выше комнаты → 422."""
    payload = {
        "city": "Казань",
        "rooms": [{
            "name": "Комната",
            "height": 2.7,
            "points": [{"x": 0, "y": 0}, {"x": 4, "y": 0}, {"x": 4, "y": 3}, {"x": 0, "y": 3}],
            "room_type": "living",
            "openings": [{"type": "door", "width": 0.8, "height": 3.0}],
            "works": W()
        }]
    }
    response = client.post("/api/estimates/calculate", json=payload)
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "высота двери" in detail.lower() or "превышать высоту" in detail


def test_window_wider_than_wall():
    """Окно шире самой длинной стены → 422."""
    payload = {
        "city": "Казань",
        "rooms": [{
            "name": "Комната",
            "height": 2.7,
            "points": [{"x": 0, "y": 0}, {"x": 4, "y": 0}, {"x": 4, "y": 3}, {"x": 0, "y": 3}],
            "room_type": "living",
            "openings": [{"type": "window", "width": 5.0, "height": 1.5}],
            "works": W()
        }]
    }
    response = client.post("/api/estimates/calculate", json=payload)
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "длину самой длинной стены" in detail.lower()


def test_total_openings_exceed_wall_area():
    """Суммарная площадь проёмов >= площади стен → 422."""
    payload = {
        "city": "Казань",
        "rooms": [{
            "name": "Комната",
            "height": 2.7,
            "points": [{"x": 0, "y": 0}, {"x": 4, "y": 0}, {"x": 4, "y": 2}, {"x": 0, "y": 2}],
            "room_type": "living",
            "openings": [
                {"type": "window", "width": 3.0, "height": 2.7},
                {"type": "window", "width": 3.0, "height": 2.7},
                {"type": "window", "width": 3.0, "height": 2.7},
                {"type": "window", "width": 3.0, "height": 2.7}
            ],
            "works": W()
        }]
    }
    response = client.post("/api/estimates/calculate", json=payload)
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "суммарная площадь проёмов" in detail.lower()


def test_door_full_wall():
    """Дверь во всю стену – wall_area корректно уменьшается, но не становится отрицательной."""
    payload = {
        "city": "Казань",
        "rooms": [{
            "name": "Комната",
            "height": 2.7,
            "points": [{"x": 0, "y": 0}, {"x": 4, "y": 0}, {"x": 4, "y": 3}, {"x": 0, "y": 3}],
            "room_type": "living",
            "openings": [{"type": "door", "width": 4.0, "height": 2.7}],
            "works": W()
        }]
    }
    response = client.post("/api/estimates/calculate", json=payload)
    assert response.status_code == 200
    data = response.json()
    # Периметр = 14, стены до вычета = 14*2.7=37.8, дверь = 4*2.7=10.8, остаётся 27.0
    assert data["geometry"]["wall_area"] == pytest.approx(27.0, 0.01)


def test_otkosy_line_present_and_grows_with_depth():
    """#191: смета с окном и дверью содержит строку «Отделка откосов» (>0),
    и площадь растёт при увеличении глубины откоса."""
    def _payload(depth=None):
        door = {"type": "door", "width": 0.8, "height": 2.0}
        window = {"type": "window", "width": 1.5, "height": 1.4}
        if depth is not None:
            door["depth"] = depth
            window["depth"] = depth
        return {
            "city": "Казань",
            "rooms": [{
                "name": "Спальня", "height": 2.7,
                "points": [{"x": 0, "y": 0}, {"x": 4, "y": 0}, {"x": 4, "y": 3}, {"x": 0, "y": 3}],
                "room_type": "living",
                "openings": [door, window],
                "works": W(),
            }],
        }

    data = client.post("/api/estimates/calculate", json=_payload()).json()
    otkos = next((lab for lab in data["labor"] if lab["service"] == "Отделка откосов"), None)
    assert otkos is not None
    assert otkos["volume"] > 0
    assert otkos["specialist"] == "Штукатур"

    deep = client.post("/api/estimates/calculate", json=_payload(depth=0.4)).json()
    otkos_deep = next(lab for lab in deep["labor"] if lab["service"] == "Отделка откосов")
    assert otkos_deep["volume"] > otkos["volume"]


def test_stretch_ceiling_gives_block_not_floor_multiplier():
    """#191: натяжной потолок отдаёт отдельные строки (полотно + закладные + ниша),
    а не скрытый множитель площади пола."""
    payload = {
        "city": "Казань",
        "rooms": [{
            "name": "Гостиная", "height": 2.7,
            "points": [{"x": 0, "y": 0}, {"x": 4, "y": 0}, {"x": 4, "y": 3}, {"x": 0, "y": 3}],
            "room_type": "living",
            "openings": [],
            "works": {
                "floor": {"enabled": False, "finish": None},
                "walls": {"enabled": False, "finish": None},
                "ceiling": {"enabled": True, "finish": "stretch",
                            "light_points": 4, "curtain_niche_m": 3.0},
                "electric": {"enabled": False},
                "plumbing": {"enabled": False},
            },
        }],
    }
    data = client.post("/api/estimates/calculate", json=payload).json()
    by_service = {lab["service"]: lab for lab in data["labor"]}

    assert "Монтаж натяжного потолка" in by_service
    assert "Закладная под светильник" in by_service
    assert "Ниша под карниз" in by_service
    # Полотно — по площади потолка (=12), не множитель площади пола.
    assert by_service["Монтаж натяжного потолка"]["volume"] == pytest.approx(12.0)
    assert by_service["Закладная под светильник"]["volume"] == pytest.approx(4.0)
    assert by_service["Ниша под карниз"]["volume"] == pytest.approx(3.0)


def test_non_positive_opening_depth_rejected():
    """#191: глубина откоса должна быть > 0 (как ширина/высота) — ≤0 отдаёт 422."""
    def _payload(depth):
        return {
            "city": "Казань",
            "rooms": [{
                "name": "Спальня", "height": 2.7,
                "points": [{"x": 0, "y": 0}, {"x": 4, "y": 0}, {"x": 4, "y": 3}, {"x": 0, "y": 3}],
                "room_type": "living",
                "openings": [{"type": "door", "width": 0.8, "height": 2.0, "depth": depth}],
                "works": W(),
            }],
        }

    assert client.post("/api/estimates/calculate", json=_payload(0)).status_code == 422
    assert client.post("/api/estimates/calculate", json=_payload(-0.1)).status_code == 422


def test_labor_tier_consistency():
    """Проверка, что labor[] содержит полную вилку цен, а сводка согласована со строками."""
    # Базовый payload с одной комнатой
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
                ],
                "works": {
                    "floor": {"enabled": True, "finish": "laminate"},
                    "walls": {"enabled": True, "finish": "paint"},
                    "ceiling": {"enabled": True, "finish": "paint"},
                    "electric": {"enabled": True, "sockets": 5, "lights": 3, "cable_m": 20},
                    "plumbing": {"enabled": False, "pipe_m": 0}
                }
            }
        ],
        "tier": "avg"   # задаём уровень
    }

    # 1. Запрос с tier="avg"
    resp_avg = client.post("/api/estimates/calculate", json=payload)
    assert resp_avg.status_code == 200
    data_avg = resp_avg.json()
    labor_items_avg = data_avg["labor"]

    # Проверяем, что у каждой работы есть все поля вилки
    for item in labor_items_avg:
        assert "price_min" in item
        assert "price_avg" in item
        assert "price_max" in item
        assert "total_min" in item
        assert "total_avg" in item
        assert "total_max" in item
        assert item["tier"] == "avg"
        # Для avg-уровня price и total должны равняться avg
        assert item["price"] == item["price_avg"]
        assert item["total"] == item["total_avg"]

    # Проверяем согласованность сводки
    summary_avg = data_avg["summary"]
    total_avg_sum = sum(item["total_avg"] for item in labor_items_avg)
    assert total_avg_sum == pytest.approx(summary_avg["labor_avg"], 0.01)

    total_min_sum = sum(item["total_min"] for item in labor_items_avg)
    assert total_min_sum == pytest.approx(summary_avg["labor_min"], 0.01)

    total_max_sum = sum(item["total_max"] for item in labor_items_avg)
    assert total_max_sum == pytest.approx(summary_avg["labor_max"], 0.01)

    # 2. Запрос с tier="min"
    payload_min = {**payload, "tier": "min"}
    resp_min = client.post("/api/estimates/calculate", json=payload_min)
    assert resp_min.status_code == 200
    data_min = resp_min.json()
    labor_items_min = data_min["labor"]

    for item in labor_items_min:
        assert item["tier"] == "min"
        assert item["price"] == item["price_min"]
        assert item["total"] == item["total_min"]

    # 3. Запрос с tier="max"
    payload_max = {**payload, "tier": "max"}
    resp_max = client.post("/api/estimates/calculate", json=payload_max)
    assert resp_max.status_code == 200
    data_max = resp_max.json()
    labor_items_max = data_max["labor"]

    for item in labor_items_max:
        assert item["tier"] == "max"
        assert item["price"] == item["price_max"]
        assert item["total"] == item["total_max"]

    # Дополнительно: убедимся, что min < avg < max (если цены различаются)
    # Находим одну работу, которая точно есть (например, "Покраска стен")
    paint_avg = next(item for item in labor_items_avg if item["service"] == "Покраска стен")
    assert paint_avg["price_min"] < paint_avg["price_avg"] < paint_avg["price_max"]


def test_material_tier_consistency():
    """Проверка, что materials[] содержит полную вилку цен, а сводка согласована со строками."""
    # Базовый payload с одной комнатой (включая электрику для разнообразия)
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
                ],
                "works": {
                    "floor": {"enabled": True, "finish": "laminate"},
                    "walls": {"enabled": True, "finish": "paint"},
                    "ceiling": {"enabled": True, "finish": "paint"},
                    "electric": {"enabled": True, "sockets": 5, "lights": 3, "cable_m": 20},
                    "plumbing": {"enabled": False, "pipe_m": 0}
                }
            }
        ],
        "tier": "avg"   # задаём уровень
    }

    # 1. Запрос с tier="avg"
    resp_avg = client.post("/api/estimates/calculate", json=payload)
    assert resp_avg.status_code == 200
    data_avg = resp_avg.json()
    materials_avg = data_avg["materials"]

    # Проверяем, что у каждого материала есть все поля вилки
    for item in materials_avg:
        assert "price_min" in item
        assert "price_avg" in item
        assert "price_max" in item
        assert "total_min" in item
        assert "total_avg" in item
        assert "total_max" in item
        assert item["tier"] == "avg"
        # Для avg-уровня price и total должны равняться avg
        assert item["price"] == item["price_avg"]
        assert item["total"] == item["total_avg"]

    # Проверяем согласованность сводки
    summary_avg = data_avg["summary"]
    total_avg_sum = sum(item["total_avg"] for item in materials_avg)
    assert total_avg_sum == pytest.approx(summary_avg["materials_avg"], 0.01)

    total_min_sum = sum(item["total_min"] for item in materials_avg)
    assert total_min_sum == pytest.approx(summary_avg["materials_min"], 0.01)

    total_max_sum = sum(item["total_max"] for item in materials_avg)
    assert total_max_sum == pytest.approx(summary_avg["materials_max"], 0.01)

    # 2. Запрос с tier="min"
    payload_min = {**payload, "tier": "min"}
    resp_min = client.post("/api/estimates/calculate", json=payload_min)
    assert resp_min.status_code == 200
    data_min = resp_min.json()
    materials_min = data_min["materials"]

    for item in materials_min:
        assert item["tier"] == "min"
        assert item["price"] == item["price_min"]
        assert item["total"] == item["total_min"]

    # 3. Запрос с tier="max"
    payload_max = {**payload, "tier": "max"}
    resp_max = client.post("/api/estimates/calculate", json=payload_max)
    assert resp_max.status_code == 200
    data_max = resp_max.json()
    materials_max = data_max["materials"]

    for item in materials_max:
        assert item["tier"] == "max"
        assert item["price"] == item["price_max"]
        assert item["total"] == item["total_max"]

    # Дополнительно: убедимся, что min < avg < max (если цены различаются)
    # Находим один материал, который точно есть (например, "Краска для стен")
    paint_avg = next(item for item in materials_avg if item["name"] == "Краска для стен")
    assert paint_avg["price_min"] < paint_avg["price_avg"] < paint_avg["price_max"]


def test_material_tier_selects_different_sku():
    """#331: tier=min/max на floor.laminate отдают РАЗНЫЕ товары (name/source_url/
    package_size), а не одну цену с разбросом (в отличие от #327/#293-интерима)."""
    payload = {
        "city": "Казань",
        "rooms": [
            {
                "name": "Спальня",
                "height": 2.7,
                "points": [
                    {"x": 0, "y": 0}, {"x": 4, "y": 0}, {"x": 4, "y": 3}, {"x": 0, "y": 3}
                ],
                "room_type": "living",
                "openings": [{"type": "door", "width": 0.8, "height": 2.0}],
                "works": {
                    "floor": {"enabled": True, "finish": "laminate"},
                    "walls": {"enabled": False, "finish": None},
                    "ceiling": {"enabled": False, "finish": None},
                    "electric": {"enabled": False},
                    "plumbing": {"enabled": False},
                }
            }
        ],
    }

    def _laminate_row(tier):
        resp = client.post("/api/estimates/calculate", json={**payload, "tier": tier})
        assert resp.status_code == 200
        materials = resp.json()["materials"]
        return next(m for m in materials if m["unit"] == "м²")

    row_min = _laminate_row("min")
    row_avg = _laminate_row("avg")
    row_max = _laminate_row("max")

    assert row_min["name"] == "Ламинат эконом"
    assert row_avg["name"] == "Ламинат"
    assert row_max["name"] == "Ламинат премиум"
    # package_size различается по варианту → у quantity/packs тоже другое число,
    # не только цена (как проверить из issue #331).
    assert row_min["package_size"] == 1.5
    assert row_max["package_size"] == 2.5
    assert row_min["packs"] != row_max["packs"]


def test_missing_price_handled_gracefully(monkeypatch):
    """Проверка, что при отсутствии цены у материала (get_material_price возвращает None)
    ответ остаётся 200, строка присутствует со source='нет цены' и все ценовые поля = 0.
    """
    # Подменяем get_material_price в модуле app.api.estimates, где она используется
    def mock_get_material_price(*args, **kwargs):
        return None
    monkeypatch.setattr("app.api.estimates.get_material_price", mock_get_material_price)

    payload = {
        "city": "Казань",
        "rooms": [{
            "name": "Спальня",
            "height": 2.7,
            "points": [{"x": 0, "y": 0}, {"x": 4, "y": 0}, {"x": 4, "y": 3}, {"x": 0, "y": 3}],
            "room_type": "living",
            "openings": [],
            "works": {
                "floor": {"enabled": True, "finish": "laminate"},
                "walls": {"enabled": True, "finish": "paint"},
                "ceiling": {"enabled": False, "finish": None},
                "electric": {"enabled": False},
                "plumbing": {"enabled": False},
            }
        }],
        "tier": "avg"
    }
    response = client.post("/api/estimates/calculate", json=payload)
    assert response.status_code == 200
    data = response.json()

    for item in data["materials"]:
        assert item["source"] == "нет цены"
        assert item["price"] == 0.0
        assert item["total"] == 0.0
        assert item["price_min"] == 0.0
        assert item["price_avg"] == 0.0
        assert item["price_max"] == 0.0
        assert item["total_min"] == 0.0
        assert item["total_avg"] == 0.0
        assert item["total_max"] == 0.0
        assert item["tier"] == "avg"

