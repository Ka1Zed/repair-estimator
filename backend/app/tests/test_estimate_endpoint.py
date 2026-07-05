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
    """Блок скрытых работ одинаков при finish_only и rough_and_finish (#239).

    Скрытые работы — риск неизвестного основания, ортогональный глубине сметы:
    в summary они не входят ни при каком scope, состав от scope не зависит.
    """
    finish = client.post("/api/estimates/calculate",
                         json=_bathroom_payload("finish_only")).json()
    rough = client.post("/api/estimates/calculate",
                        json=_bathroom_payload("rough_and_finish")).json()

    def services(d):
        return {x["service"] for x in d["hidden_works"]["items"]}

    assert services(finish) == services(rough)
    assert finish["hidden_works"]["total_avg"] == pytest.approx(
        rough["hidden_works"]["total_avg"])


def test_invalid_scope_rejected():
    """Неизвестный scope отклоняется валидацией (422)."""
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
