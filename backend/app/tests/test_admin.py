# app/tests/test_admin.py
#
# Тесты admin-роутера PATCH цен (#233). Эндпоинты ходят в БД через SessionLocal
# напрямую (не get_db), а он в тестах уже привязан к тестовому engine (env в
# conftest выставляется до импорта app.*), поэтому запись идёт в тестовую БД.
# Тесты МУТИРУЮТ БД → isolated_seeded_db (пере-seed до/после). Источник "manual"
# в тестовом посеве отсутствует — добавляем его сами.

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.models import Material, LaborService, PriceSource, MaterialPrice, LaborPrice
from app.tests.conftest import TestingSessionLocal

client = TestClient(app)


@pytest.fixture
def manual_source(isolated_seeded_db):
    """Гарантирует наличие источника manual и отдаёт валидные id материала/работы."""
    db = TestingSessionLocal()
    try:
        if db.query(PriceSource).filter(PriceSource.name == "manual").first() is None:
            db.add(PriceSource(name="manual", type="manual", url=None))
            db.commit()
        material_id = db.query(Material).first().id
        labor_id = db.query(LaborService).first().id
    finally:
        db.close()
    return {"material_id": material_id, "labor_id": labor_id}


def _valid_body():
    return {"price_min": 100, "price_avg": 120, "price_max": 140, "region": "Казань"}


def test_create_manual_material_price(manual_source):
    material_id = manual_source["material_id"]
    resp = client.patch(f"/api/admin/material-prices/{material_id}", json=_valid_body())
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["material_id"] == material_id
    assert data["source"] == "manual"
    assert float(data["price_avg"]) == 120

    # запись реально создана в БД с source=manual
    db = TestingSessionLocal()
    try:
        source = db.query(PriceSource).filter(PriceSource.name == "manual").first()
        row = db.query(MaterialPrice).filter(
            MaterialPrice.material_id == material_id,
            MaterialPrice.source_id == source.id,
        ).first()
        assert row is not None
        assert float(row.price_max) == 140
    finally:
        db.close()


def test_update_existing_manual_material_price(manual_source):
    material_id = manual_source["material_id"]
    client.patch(f"/api/admin/material-prices/{material_id}", json=_valid_body())

    # второй PATCH обновляет ту же строку, а не плодит новую
    updated = {"price_min": 200, "price_avg": 250, "price_max": 300, "region": "Москва"}
    resp = client.patch(f"/api/admin/material-prices/{material_id}", json=updated)
    assert resp.status_code == 200, resp.text
    assert float(resp.json()["price_avg"]) == 250

    db = TestingSessionLocal()
    try:
        source = db.query(PriceSource).filter(PriceSource.name == "manual").first()
        rows = db.query(MaterialPrice).filter(
            MaterialPrice.material_id == material_id,
            MaterialPrice.source_id == source.id,
        ).all()
        assert len(rows) == 1
        assert float(rows[0].price_min) == 200
        assert rows[0].region == "Москва"
    finally:
        db.close()


def test_update_labor_price(manual_source):
    labor_id = manual_source["labor_id"]
    resp = client.patch(f"/api/admin/labor-prices/{labor_id}", json=_valid_body())
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["labor_service_id"] == labor_id
    assert data["source"] == "manual"

    db = TestingSessionLocal()
    try:
        source = db.query(PriceSource).filter(PriceSource.name == "manual").first()
        row = db.query(LaborPrice).filter(
            LaborPrice.labor_service_id == labor_id,
            LaborPrice.source_id == source.id,
        ).first()
        assert row is not None
    finally:
        db.close()


def test_material_price_unknown_id_returns_404(manual_source):
    resp = client.patch("/api/admin/material-prices/999999", json=_valid_body())
    assert resp.status_code == 404, resp.text


def test_labor_price_unknown_id_returns_404(manual_source):
    resp = client.patch("/api/admin/labor-prices/999999", json=_valid_body())
    assert resp.status_code == 404, resp.text


def test_material_price_bad_order_returns_422(manual_source):
    material_id = manual_source["material_id"]
    bad = {"price_min": 300, "price_avg": 120, "price_max": 140}
    resp = client.patch(f"/api/admin/material-prices/{material_id}", json=bad)
    assert resp.status_code == 422, resp.text


def test_material_price_zero_min_returns_422(manual_source):
    material_id = manual_source["material_id"]
    bad = {"price_min": 0, "price_avg": 120, "price_max": 140}
    resp = client.patch(f"/api/admin/material-prices/{material_id}", json=bad)
    assert resp.status_code == 422, resp.text
