# app/tests/test_reference_endpoints.py
# Смоук справочных эндпоинтов (200 + форма ответа) и HTTP-теста геометрии
# POST /api/rooms/calculate. Справочники материалов/работ/регионов ходят в БД
# через get_db → берём тестовую БД фикстурой override_get_db (см. conftest #174).

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.mark.usefixtures("override_get_db")
def test_room_types_shape():
    resp = client.get("/api/room-types")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["roomTypes"], dict)
    assert isinstance(data["finishOptions"], dict)


@pytest.mark.usefixtures("override_get_db")
def test_materials_shape():
    resp = client.get("/api/materials")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0
    for field in ("id", "name", "category", "unit", "package_size"):
        assert field in data[0]


@pytest.mark.usefixtures("override_get_db")
def test_labor_services_shape():
    resp = client.get("/api/labor-services")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0
    for field in ("id", "name", "specialist_type", "unit"):
        assert field in data[0]


@pytest.mark.usefixtures("override_get_db")
def test_regions_shape():
    resp = client.get("/api/regions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["default"] == "Казань"
    assert isinstance(data["regions"], list)
    # Город по умолчанию всегда в списке; сид добавляет региональные цены Москвы.
    assert "Казань" in data["regions"]
    assert "Москва" in data["regions"]


# --- POST /api/rooms/calculate: геометрия по контуру (сервис покрыт, эндпоинт — нет) ---


def test_rooms_calculate_rectangle():
    '''Прямоугольник 4×3, высота 2.7: геометрия совпадает с ручным счётом.'''
    payload = {
        "height": 2.7,
        "points": [
            {"x": 0, "y": 0}, {"x": 4, "y": 0},
            {"x": 4, "y": 3}, {"x": 0, "y": 3},
        ],
    }
    resp = client.post("/api/rooms/calculate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["floor_area"] == pytest.approx(12.0)
    assert data["ceiling_area"] == pytest.approx(12.0)
    assert data["perimeter"] == pytest.approx(14.0)
    # wall_area = 14 * 2.7 = 37.8 (без проёмов)
    assert data["wall_area"] == pytest.approx(37.8, 0.01)


def test_rooms_calculate_l_shaped():
    '''Г-образная (невыпуклая) комната: shoelace и периметр по контуру.'''
    payload = {
        "height": 2.7,
        "points": [
            {"x": 0, "y": 0}, {"x": 6, "y": 0},
            {"x": 6, "y": 2}, {"x": 3, "y": 2},
            {"x": 3, "y": 5}, {"x": 0, "y": 5},
        ],
    }
    resp = client.post("/api/rooms/calculate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    # area = 6*5 - 3*3 = 21; perimeter = 6+2+3+3+3+5 = 22
    assert data["floor_area"] == pytest.approx(21.0)
    assert data["ceiling_area"] == pytest.approx(21.0)
    assert data["perimeter"] == pytest.approx(22.0)
    # wall_area = 22 * 2.7 = 59.4 (без проёмов)
    assert data["wall_area"] == pytest.approx(59.4, 0.01)


def test_rooms_calculate_subtracts_openings():
    '''Проёмы (Opening-модели) вычитаются из площади стен: эндпоинт конвертирует
    их в dict для geometry_service, иначе wall_area падал 422 (op_type,w,h = op).'''
    payload = {
        "height": 2.7,
        "points": [
            {"x": 0, "y": 0}, {"x": 4, "y": 0},
            {"x": 4, "y": 3}, {"x": 0, "y": 3},
        ],
        "openings": [
            {"type": "door", "width": 0.8, "height": 2.0},
            {"type": "window", "width": 1.5, "height": 1.4},
        ],
    }
    resp = client.post("/api/rooms/calculate", json=payload)
    assert resp.status_code == 200
    # wall_area = 14*2.7 - (0.8*2.0 + 1.5*1.4) = 37.8 - 3.7 = 34.1
    assert resp.json()["wall_area"] == pytest.approx(34.1, 0.01)


def test_rooms_calculate_invalid_opening_rejected():
    '''Дверь выше комнаты → доменная ошибка geometry_service отдаётся как 422.'''
    payload = {
        "height": 2.7,
        "points": [
            {"x": 0, "y": 0}, {"x": 4, "y": 0},
            {"x": 4, "y": 3}, {"x": 0, "y": 3},
        ],
        "openings": [{"type": "door", "width": 0.8, "height": 3.0}],
    }
    resp = client.post("/api/rooms/calculate", json=payload)
    assert resp.status_code == 422


def test_rooms_calculate_too_few_points_rejected():
    '''Меньше 3 точек — 422 (валидация схемы).'''
    payload = {"height": 2.7, "points": [{"x": 0, "y": 0}, {"x": 4, "y": 0}]}
    resp = client.post("/api/rooms/calculate", json=payload)
    assert resp.status_code == 422
