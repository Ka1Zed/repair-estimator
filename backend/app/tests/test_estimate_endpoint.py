import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import SessionLocal
from app.db.models import Material
from app.db.seed import seed  # предполагаем, что seed лежит в app.db.seed

client = TestClient(app)


def ensure_seed_data():
    """Проверяет наличие данных в БД, при необходимости вызывает seed."""
    session = SessionLocal()
    try:
        # Проверяем, есть ли хотя бы один материал
        material = session.query(Material).first()
        if material is None:
            # Данных нет — заливаем seed
            seed()
    finally:
        session.close()


@pytest.fixture(scope="session", autouse=True)
def setup_db():
    """Фикстура, выполняющаяся один раз перед всеми тестами."""
    ensure_seed_data()
    yield


def test_single_room():
    """Проверка запроса с одной комнатой."""
    session = SessionLocal()
    count = session.query(Material).count()
    print(f"DEBUG: total materials in DB = {count}")
    if count > 0:
        for m in session.query(Material).limit(5).all():
            print(f"  - {m.name}")
    session.close()
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
            "tile": False,
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
    painter = next((l for l in labor if l["service"] == "Покраска стен"), None)
    assert painter is not None

    # Проверка summary: min <= avg <= max
    summary = data["summary"]
    assert summary["materials_min"] <= summary["materials_avg"] <= summary["materials_max"]
    assert summary["labor_min"] <= summary["labor_avg"] <= summary["labor_max"]
    assert summary["total_min"] <= summary["total_avg"] <= summary["total_max"]


def test_two_rooms():
    """Проверка: две одинаковые комнаты -> удвоение количества и итога."""
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
            "tile": False,
            "electric": "basic",
            "plumbing": False
        }
    }

    response = client.post("/api/estimates/calculate", json=payload)
    assert response.status_code == 200
    data = response.json()

    # Проверяем, что ламинат имеет удвоенное количество
    laminate = next((m for m in data["materials"] if m["name"] == "Ламинат"), None)
    assert laminate is not None
    # Площадь пола 12, запас 8% -> 12*1.08 = 12.96, две комнаты -> 25.92
    assert laminate["quantity"] == pytest.approx(2 * 12 * 1.08, 0.01)


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
            "tile": False,
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
        