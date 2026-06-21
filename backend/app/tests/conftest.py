import os
import pytest
from datetime import datetime, timezone
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("POSTGRES_USER", "repair")
os.environ.setdefault("POSTGRES_PASSWORD", "repair")
os.environ.setdefault("POSTGRES_DB", "repair_estimator")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5432")

from app.db.models import Base
from app.db.session import engine
from app.main import app
from app.api.estimates import get_db
from app.db.models import Material, LaborService, PriceSource, MaterialPrice, LaborPrice

test_engine = engine
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

def seed_test_data(session):
    # Очищаем таблицы
    session.query(LaborPrice).delete()
    session.query(MaterialPrice).delete()
    session.query(LaborService).delete()
    session.query(Material).delete()
    session.query(PriceSource).delete()
    session.commit()

    # Источник
    src = PriceSource(
        name="seed",
        type="seed",
        url="http://localhost",
        last_checked=datetime.now(timezone.utc)
    )
    session.add(src)
    session.flush()

    # Материалы (с категорией)
    materials_data = [
        {"name": "Краска для стен", "category": "paint", "unit": "л", "consumption_per_m2": 0.13, "waste_factor": 1.1, "package_size": 9},
        {"name": "Краска потолочная", "category": "paint", "unit": "л", "consumption_per_m2": 0.12, "waste_factor": 1.1, "package_size": 9},
        {"name": "Грунтовка", "category": "paint", "unit": "л", "consumption_per_m2": 0.1, "waste_factor": 1.1, "package_size": 5},
        {"name": "Шпаклевка", "category": "paint", "unit": "кг", "consumption_per_m2": 1.2, "waste_factor": 1.1, "package_size": 20},
        {"name": "Ламинат", "category": "floor", "unit": "м²", "consumption_per_m2": 1.0, "waste_factor": 1.08, "package_size": 2.5},
        {"name": "Плинтус", "category": "floor", "unit": "м", "consumption_per_m2": 1.0, "waste_factor": 1.1, "package_size": 2.0},
        {"name": "Плитка", "category": "tile", "unit": "м²", "consumption_per_m2": 1.0, "waste_factor": 1.1, "package_size": 1.0},
        {"name": "Плиточный клей", "category": "tile", "unit": "кг", "consumption_per_m2": 3.5, "waste_factor": 1.1, "package_size": 25},
        {"name": "Затирка", "category": "tile", "unit": "кг", "consumption_per_m2": 0.5, "waste_factor": 1.1, "package_size": 2},
        {"name": "Обои", "category": "wall", "unit": "рулон", "consumption_per_m2": 0.2, "waste_factor": 1.1, "package_size": 1},
    ]
    for m in materials_data:
        mat = Material(**m)
        session.add(mat)
    session.flush()

    for mat in session.query(Material).all():
        mp = MaterialPrice(material_id=mat.id, source_id=src.id, price_min=100, price_avg=120, price_max=140)
        session.add(mp)

    # Услуги 
    services_data = [
        {"name": "Покраска стен", "specialist_type": "Маляр", "unit": "м²"},
        {"name": "Шпаклевка стен", "specialist_type": "Маляр", "unit": "м²"},
        {"name": "Покраска потолка", "specialist_type": "Маляр", "unit": "м²"},
        {"name": "Укладка ламината", "specialist_type": "Укладчик", "unit": "м²"},
        {"name": "Укладка плитки", "specialist_type": "Плиточник", "unit": "м²"},
        {"name": "Электромонтаж", "specialist_type": "Электрик", "unit": "точка"},
        {"name": "Сантехнические работы", "specialist_type": "Сантехник", "unit": "точка"},
    ]
    for s in services_data:
        svc = LaborService(**s)
        session.add(svc)
    session.flush()

    for svc in session.query(LaborService).all():
        lp = LaborPrice(labor_service_id=svc.id, source_id=src.id, price_min=300, price_avg=450, price_max=600)
        session.add(lp)

    session.commit()

@pytest.fixture(scope="session")
def setup_test_db():
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    session = TestingSessionLocal()
    seed_test_data(session)
    session.close()
    yield

@pytest.fixture
def override_get_db(setup_test_db):
    def _override():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()
    app.dependency_overrides[get_db] = _override
    yield
    app.dependency_overrides.pop(get_db, None)

@pytest.fixture
def db_session():
    """Возвращает тестовую сессию БД для модульных тестов сервисов."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()