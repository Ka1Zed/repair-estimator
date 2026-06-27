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
    src_megastroy = PriceSource(
        name="Мегастрой",
        type="parser",
        url="https://megastroy.com",
        last_checked=datetime.now(timezone.utc)
    )
    # Источники региональных парсеров работ (#166).
    src_garant = PriceSource(
        name="garantstroikompleks.ru", type="parser",
        url="https://garantstroikompleks.ru/prajs-list",
        last_checked=datetime.now(timezone.utc),
    )
    src_remont_uroven = PriceSource(
        name="remont-uroven.ru", type="parser",
        url="https://remont-uroven.ru/price.html",
        last_checked=datetime.now(timezone.utc),
    )
    src_otdelka = PriceSource(
        name="otdelka-spb.ru", type="parser",
        url="https://otdelka-spb.ru/prajjs/",
        last_checked=datetime.now(timezone.utc),
    )
    src_prorabneva = PriceSource(
        name="prorabneva.ru", type="parser",
        url="https://www.prorabneva.ru/price",
        last_checked=datetime.now(timezone.utc),
    )
    session.add(src)
    session.add(src_megastroy)
    session.add(src_garant)
    session.add(src_remont_uroven)
    session.add(src_otdelka)
    session.add(src_prorabneva)
    session.flush()

    # Материалы (с категорией)
    materials_data = [
        {"name": "Краска для стен", "category": "paint", "unit": "л", "consumption_per_m2": 0.13, "waste_factor": 1.1, "package_size": 9},
        {"name": "Краска потолочная", "category": "paint", "unit": "л", "consumption_per_m2": 0.15, "waste_factor": 1.1, "package_size": 9},
        {"name": "Грунтовка", "category": "paint", "unit": "л", "consumption_per_m2": 0.12, "waste_factor": 1.1, "package_size": 10},
        {"name": "Шпаклевка", "category": "paint", "unit": "кг", "consumption_per_m2": 1.0, "waste_factor": 1.1, "package_size": 25},
        {"name": "Ламинат", "category": "floor", "unit": "м²", "consumption_per_m2": 1.0, "waste_factor": 1.08, "package_size": 2.0},
        {"name": "Плинтус", "category": "floor", "unit": "м", "consumption_per_m2": 1.0, "waste_factor": 1.05, "package_size": 1.0},
        {"name": "Плитка", "category": "tile", "unit": "м²", "consumption_per_m2": 1.0, "waste_factor": 1.1, "package_size": 1.2},
        {"name": "Плиточный клей", "category": "tile", "unit": "кг", "consumption_per_m2": 4.5, "waste_factor": 1.1, "package_size": 25},
        {"name": "Затирка", "category": "tile", "unit": "кг", "consumption_per_m2": 0.4, "waste_factor": 1.1, "package_size": 2},
        {"name": "Обои", "category": "wall", "unit": "рулон", "consumption_per_m2": 0.2, "waste_factor": 1.1, "package_size": 1},
        {"name": "Линолеум", "category": "floor", "unit": "м²", "consumption_per_m2": 1.0, "waste_factor": 1.05, "package_size": 1.0},
    ]
    for m in materials_data:
        mat = Material(**m)
        session.add(mat)
    session.flush()

    for mat in session.query(Material).all():
        mp = MaterialPrice(material_id=mat.id, source_id=src.id, price_min=100, price_avg=120, price_max=140)
        session.add(mp)

    # Региональная seed-цена для теста регионального lookup (#127):
    # отличается от базовой (avg 200 против 120), чтобы выбор региона был заметен.
    paint = session.query(Material).filter(Material.name == "Краска для стен").first()
    session.add(MaterialPrice(
        material_id=paint.id, source_id=src.id,
        price_min=180, price_avg=200, price_max=240, region="Москва",
    ))

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

    # Региональная seed-цена работы (#127): отличается от базовой (avg 700 против 450).
    paint_walls = session.query(LaborService).filter(LaborService.name == "Покраска стен").first()
    session.add(LaborPrice(
        labor_service_id=paint_walls.id, source_id=src.id,
        price_min=600, price_avg=700, price_max=800, region="Москва",
    ))

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
def db_session(setup_test_db):
    """Возвращает тестовую сессию БД для модульных тестов сервисов.
    Зависит от setup_test_db, чтобы таблицы были созданы и заполнены."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

