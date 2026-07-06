import os
import pytest
from datetime import datetime, timezone
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("POSTGRES_USER", "repair")
os.environ.setdefault("POSTGRES_PASSWORD", "repair")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5432")

# --- Изоляция тестовой БД (#169) ---
# Тесты НИКОГДА не должны писать в dev-базу repair_estimator: фикстуры дропают
# таблицы и заливают тестовые цены (avg=120), что раньше затирало боевой seed.
# Поднимаем отдельную БД (по умолчанию repair_estimator_test) и направляем туда
# ВЕСЬ engine приложения — env выставляем ДО импорта app.*, иначе SessionLocal
# в сервисах (price_aggregator, admin, room_types) свяжется с боевым engine.
os.environ["POSTGRES_DB"] = os.environ.get("POSTGRES_TEST_DB", "repair_estimator_test")

from app.core.config import settings  # noqa: E402 — читает уже тестовый POSTGRES_DB


def _ensure_test_database() -> None:
    """Создаёт тестовую БД, если её ещё нет.

    CREATE DATABASE нельзя выполнить внутри транзакции, поэтому подключаемся к
    служебной базе postgres в autocommit. Учётные данные берём из settings —
    из того же источника, что и боевой engine, чтобы не разъехаться по паролю.
    """
    import psycopg

    conn = psycopg.connect(
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD.get_secret_value(),
        dbname="postgres",
        autocommit=True,
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (settings.POSTGRES_DB,))
            if cur.fetchone() is None:
                cur.execute(f'CREATE DATABASE "{settings.POSTGRES_DB}"')
    finally:
        conn.close()


_ensure_test_database()

from app.db.models import Base  # noqa: E402 — импорт только после настройки тестовой БД
from app.db.session import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.api.estimates import get_db, get_material_parser  # noqa: E402
from app.db.models import Material, LaborService, PriceSource, MaterialPrice, LaborPrice  # noqa: E402
from app.parsers.base import BaseParser, ParsedPrice  # noqa: E402

test_engine = engine
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

def seed_test_data(session):
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
        {"name": "Шпаклевка стартовая", "category": "paint", "unit": "кг", "consumption_per_m2": 5.0, "waste_factor": 1.1, "package_size": 30},
        {"name": "Шпаклевка финишная", "category": "paint", "unit": "кг", "consumption_per_m2": 1.0, "waste_factor": 1.1, "package_size": 25},
        {"name": "Ламинат", "category": "floor", "unit": "м²", "consumption_per_m2": 1.0, "waste_factor": 1.15, "package_size": 2.0},
        {"name": "Плинтус", "category": "floor", "unit": "м", "consumption_per_m2": 1.0, "waste_factor": 1.05, "package_size": 1.0},
        {"name": "Плитка", "category": "tile", "unit": "м²", "consumption_per_m2": 1.0, "waste_factor": 1.15, "package_size": 1.2},
        {"name": "Плиточный клей", "category": "tile", "unit": "кг", "consumption_per_m2": 4.5, "waste_factor": 1.1, "package_size": 25},
        {"name": "Затирка", "category": "tile", "unit": "кг", "consumption_per_m2": 0.4, "waste_factor": 1.1, "package_size": 2},
        {"name": "Обои", "category": "wall", "unit": "рулон", "consumption_per_m2": 0.2, "waste_factor": 1.1, "package_size": 1},
        {"name": "Линолеум", "category": "floor", "unit": "м²", "consumption_per_m2": 1.0, "waste_factor": 1.05, "package_size": 1.0},
        {"name": "Паркетная доска", "category": "floor", "unit": "м²", "consumption_per_m2": 1.0, "waste_factor": 1.15, "package_size": 2.0},
        {"name": "Краска влагостойкая", "category": "paint", "unit": "л", "consumption_per_m2": 0.13, "waste_factor": 1.1, "package_size": 9},
        # Инженерка (works.electric / works.plumbing) — количество из запроса, не по норме.
        {"name": "Кабель электрический", "category": "electric", "unit": "м", "waste_factor": 1.1, "package_size": 1.0},
        {"name": "Розетка", "category": "electric", "unit": "шт", "package_size": 1},
        {"name": "Светильник", "category": "electric", "unit": "шт", "package_size": 1},
        {"name": "Труба водопроводная", "category": "plumbing", "unit": "м", "waste_factor": 1.1, "package_size": 2.0},
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
        {"name": "Поклейка обоев", "specialist_type": "Маляр", "unit": "м²"},
        {"name": "Укладка ламината", "specialist_type": "Укладчик", "unit": "м²"},
        {"name": "Укладка линолеума", "specialist_type": "Укладчик", "unit": "м²"},
        {"name": "Укладка паркета", "specialist_type": "Паркетчик", "unit": "м²"},
        {"name": "Укладка плитки", "specialist_type": "Плиточник", "unit": "м²"},
        {"name": "Монтаж натяжного потолка", "specialist_type": "Потолочник", "unit": "м²"},
        # Натяжной потолок блоком + откосы (#191).
        {"name": "Закладная под светильник", "specialist_type": "Потолочник", "unit": "шт"},
        {"name": "Ниша под карниз", "specialist_type": "Потолочник", "unit": "м"},
        {"name": "Отделка откосов", "specialist_type": "Штукатур", "unit": "м²"},
        {"name": "Электромонтаж", "specialist_type": "Электрик", "unit": "точка"},
        {"name": "Штробление", "specialist_type": "Электрик", "unit": "м"},
        {"name": "Сантехнические работы", "specialist_type": "Сантехник", "unit": "точка"},
        # Гранулярная инженерка works (#222).
        {"name": "Прокладка кабеля", "specialist_type": "Электрик", "unit": "м"},
        {"name": "Монтаж розетки", "specialist_type": "Электрик", "unit": "шт"},
        {"name": "Монтаж светильника", "specialist_type": "Электрик", "unit": "шт"},
        {"name": "Монтаж труб", "specialist_type": "Сантехник", "unit": "м"},
        # Черновые работы (#190).
        {"name": "Демонтаж", "specialist_type": "Разнорабочий", "unit": "м²"},
        {"name": "Выравнивание стен", "specialist_type": "Штукатур", "unit": "м²"},
        {"name": "Стяжка пола", "specialist_type": "Стяжечник", "unit": "м²"},
        {"name": "Гидроизоляция", "specialist_type": "Гидроизолировщик", "unit": "м²"},
        {"name": "Грунтование", "specialist_type": "Маляр", "unit": "м²"},
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


@pytest.fixture
def isolated_seeded_db(setup_test_db):
    """Изолированная копия стандартного посева для тестов, которые МУТИРУЮТ БД
    (удаляют/добавляют строки, пишут цены). Пересобирает каноничное состояние
    до и после теста, чтобы не поехали другие тесты на общей session-scoped БД."""
    def _rebuild():
        Base.metadata.drop_all(bind=test_engine)
        Base.metadata.create_all(bind=test_engine)
        session = TestingSessionLocal()
        seed_test_data(session)
        session.close()

    _rebuild()
    yield
    _rebuild()


# --- Герметизация эндпоинт-тестов от сети (#174) ---
# /api/estimates/calculate берёт цены материалов через парсер. Чтобы тесты не
# тащили живой Мегастрой (флак на VPN/офлайн/смене вёрстки), парсер инжектится
# через зависимость get_material_parser и подменяется этой заглушкой.

class _StubMaterialParser(BaseParser):
    """Заглушка парсера материалов: НЕ ходит в сеть.

    По умолчанию падает → агрегатор откатывается на seed. Можно задать callable
    fetch(material_name) -> ParsedPrice, чтобы проверить ветку «цена от парсера»."""

    source_name = "Мегастрой"

    def __init__(self, fetch=None):
        self._fetch = fetch

    def fetch_price(self, material_name: str) -> ParsedPrice:
        if self._fetch is None:
            raise RuntimeError("парсер материалов отключён в тестах (#174)")
        return self._fetch(material_name)


def _clear_parser_material_prices() -> None:
    """Чистит осевшие в общей тест-БД parser-цены материалов (всё, что не seed).

    TTL-кэш иначе оставил бы свежую parser-цену между тестами и она перекрыла бы
    seed — выбор источника стал бы зависеть от порядка прогона."""
    db = TestingSessionLocal()
    try:
        seed = db.query(PriceSource).filter(PriceSource.name == "seed").first()
        db.query(MaterialPrice).filter(MaterialPrice.source_id != seed.id).delete()
        db.commit()
    finally:
        db.close()


@pytest.fixture
def stub_material_parser():
    """Общая заглушка парсера материалов для эндпоинт-тестов.

    По умолчанию парсер падает → цены материалов берутся из seed, сети нет.
    Возвращает настройщик: вызови stub_material_parser(fetch) с функцией
    fetch(material_name) -> ParsedPrice, чтобы протестировать ветку парсера."""

    def _install(fetch=None):
        _clear_parser_material_prices()
        app.dependency_overrides[get_material_parser] = lambda: _StubMaterialParser(fetch)

    _install()  # дефолт — падающий парсер, гарантированный seed
    yield _install
    app.dependency_overrides.pop(get_material_parser, None)

