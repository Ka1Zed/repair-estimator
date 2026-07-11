# app/tests/test_project_endpoints.py
# CRUD /api/projects + публичная read-only ссылка-шеринг по share_token (#295).
# Не требует парсера цен — не используем stub_material_parser, только override_get_db.

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _room_payload():
    return {
        "name": "Гостиная",
        "height": 2.7,
        "points": [
            {"x": 0, "y": 0}, {"x": 4, "y": 0},
            {"x": 4, "y": 3}, {"x": 0, "y": 3},
        ],
        "room_type": "living",
        "openings": [],
    }


def _project_payload(name="Мой проект"):
    return {
        "name": name,
        "city": "Казань",
        "rooms": [_room_payload()],
        "scope": "finish_only",
    }


@pytest.mark.usefixtures("override_get_db")
def test_create_and_get_project_round_trip():
    created = client.post("/api/projects", json=_project_payload())
    assert created.status_code == 201
    data = created.json()
    assert data["name"] == "Мой проект"
    assert data["city"] == "Казань"
    assert len(data["rooms"]) == 1
    assert data["scope"] == "finish_only"
    assert data["share_token"]

    fetched = client.get(f"/api/projects/{data['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == data


@pytest.mark.usefixtures("override_get_db")
def test_list_contains_created_project():
    created = client.post("/api/projects", json=_project_payload("Список: проект"))
    project_id = created.json()["id"]

    listed = client.get("/api/projects")
    assert listed.status_code == 200
    ids = [p["id"] for p in listed.json()]
    assert project_id in ids
    # Список лёгкий — без rooms/share_token.
    item = next(p for p in listed.json() if p["id"] == project_id)
    assert "rooms" not in item
    assert "share_token" not in item


@pytest.mark.usefixtures("override_get_db")
def test_update_project_replaces_plan():
    created = client.post("/api/projects", json=_project_payload("До правки"))
    project_id = created.json()["id"]

    updated_payload = _project_payload("После правки")
    updated_payload["rooms"][0]["name"] = "Спальня"
    updated = client.put(f"/api/projects/{project_id}", json=updated_payload)
    assert updated.status_code == 200
    data = updated.json()
    assert data["name"] == "После правки"
    assert data["rooms"][0]["name"] == "Спальня"
    # share_token не меняется при обновлении плана.
    assert data["share_token"] == created.json()["share_token"]


@pytest.mark.usefixtures("override_get_db")
def test_delete_project_then_404():
    created = client.post("/api/projects", json=_project_payload("На удаление"))
    project_id = created.json()["id"]

    deleted = client.delete(f"/api/projects/{project_id}")
    assert deleted.status_code == 204

    fetched = client.get(f"/api/projects/{project_id}")
    assert fetched.status_code == 404


@pytest.mark.usefixtures("override_get_db")
def test_get_nonexistent_project_404():
    resp = client.get("/api/projects/999999")
    assert resp.status_code == 404


@pytest.mark.usefixtures("override_get_db")
def test_share_token_returns_readonly_project():
    created = client.post("/api/projects", json=_project_payload("Шеринг"))
    share_token = created.json()["share_token"]

    shared = client.get(f"/api/projects/share/{share_token}")
    assert shared.status_code == 200
    data = shared.json()
    assert data["name"] == "Шеринг"
    assert len(data["rooms"]) == 1
    # Публичный ответ не содержит id/share_token — не даёт зацепки для правки.
    assert "id" not in data
    assert "share_token" not in data


@pytest.mark.usefixtures("override_get_db")
def test_share_token_unknown_404():
    resp = client.get("/api/projects/share/does-not-exist")
    assert resp.status_code == 404
