import os
import pytest
from datetime import datetime, timezone
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("POSTGRES_USER", "repair")
os.environ.setdefault("POSTGRES_PASSWORD", "repair")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5432")

# --- Изоляция тестовой БД (#169, per-process — #263) ---
# Тесты НИКОГДА не должны писать в dev-базу repair_estimator: фикстуры дропают
# таблицы и заливают тестовые цены (avg=120), что раньше затирало боевой seed.
# Поднимаем отдельную БД и направляем туда ВЕСЬ engine приложения — env выставляем
# ДО импорта app.*, иначе SessionLocal в сервисах (price_aggregator, admin,
# room_types) свяжется с боевым engine.
#
# Имя БД делаем УНИКАЛЬНЫМ на процесс: два одновременных прогона pytest (два
# терминала / локалка + CI на том же Postgres / xdist-воркеры) иначе бьют в одну
# базу и ловят ложные падения, пока сосед выполняет drop_all→create_all→seed на
# полусозданной схеме (#263). Суффикс берём из PYTEST_XDIST_WORKER (при -n), иначе
# из PID. POSTGRES_TEST_DB, если задан явно, перекрывает генерацию (для отладки на
# фиксированной базе — тогда межпроцессной изоляции нет, это осознанный выбор).
_worker_tag = os.environ.get("PYTEST_XDIST_WORKER") or f"pid{os.getpid()}"
_explicit_test_db = "POSTGRES_TEST_DB" in os.environ
os.environ["POSTGRES_DB"] = os.environ.get(
    "POSTGRES_TEST_DB", f"repair_estimator_test_{_worker_tag}"
)

from app.core.config import settings  # noqa: E402 — читает уже тестовый POSTGRES_DB


# Дропаем в session-teardown только per-process базу, ИМЯ которой сгенерировали мы
# сами (repair_estimator_test_<worker|pid>). Явную фиксированную POSTGRES_TEST_DB не
# трогаем — она может быть общей/отладочной, снести её значило бы задеть соседа. Владение
# по имени, а не по факту создания: так подчищаем и stale-базу от упавшего прогона с тем же PID.
_owns_test_db = not _explicit_test_db


def _service_conn():
    """Autocommit-подключение к служебной БД postgres для DDL над тест-базой.

    CREATE/DROP DATABASE нельзя выполнить внутри транзакции. Учётные данные берём
    из settings — из того же источника, что и боевой engine, чтобы не разъехаться
    по паролю."""
    import psycopg

    return psycopg.connect(
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD.get_secret_value(),
        dbname="postgres",
        autocommit=True,
    )


def _ensure_test_database() -> None:
    """Создаёт тестовую БД, если её ещё нет."""
    conn = _service_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (settings.POSTGRES_DB,))
            if cur.fetchone() is None:
                cur.execute(f'CREATE DATABASE "{settings.POSTGRES_DB}"')
    finally:
        conn.close()


def _drop_test_database() -> None:
    """Убирает per-process тест-базу в конце сессии, чтобы не копить
    repair_estimator_test_* на Postgres (#263).

    Сначала гасим свои же соединения (engine.dispose закрывает пул, но подстрахуемся
    pg_terminate_backend), потом DROP DATABASE — иначе Postgres не отдаст занятую базу."""
    # engine мог не успеть импортироваться, если app.* упал при импорте после CREATE
    # DATABASE — берём осторожно, чтобы teardown не замаскировал исходную ошибку NameError.
    _eng = globals().get("engine")
    if _eng is not None:
        _eng.dispose()
    conn = _service_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (settings.POSTGRES_DB,),
            )
            cur.execute(f'DROP DATABASE IF EXISTS "{settings.POSTGRES_DB}"')
    finally:
        conn.close()


_ensure_test_database()


def pytest_sessionfinish(session, exitstatus):
    """Прибираем per-process тест-базу после сессии (только если имя сгенерировали сами)."""
    if _owns_test_db:
        _drop_test_database()

from app.db.models import Base  # noqa: E402 — импорт только после настройки тестовой БД
from app.db.session import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.api.estimates import get_db, get_material_parsers  # noqa: E402
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
    # Второй источник материалов — Леман (Казань/Москва/СПб делят один source_id,
    # цены разводятся по MaterialPrice.region, #345). Нужен, чтобы эндпоинт-тесты
    # могли проверить объединение источников и выбор регионального парсера.
    src_leman = PriceSource(
        name="Леман",
        type="parser",
        url="https://lemanapro.ru",
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
    session.add(src_leman)
    session.add(src_garant)
    session.add(src_remont_uroven)
    session.add(src_otdelka)
    session.add(src_prorabneva)
    session.flush()

    # Материалы (с категорией). slug — как в seed_data/materials.json (#278).
    materials_data = [
        {"name": "Краска для стен", "slug": "paint_walls", "category": "paint", "unit": "л", "consumption_per_m2": 0.13, "waste_factor": 1.1, "package_size": 9, "layers": 2, "finish_key": "walls.paint", "variant_tier": "avg", "category_exclusions": ["drevesin", "po-metall", "fasad"]},
        {"name": "Краска потолочная", "slug": "paint_ceiling", "category": "paint", "unit": "л", "consumption_per_m2": 0.15, "waste_factor": 1.1, "package_size": 9, "layers": 2, "finish_key": "ceiling.paint", "variant_tier": "avg", "category_exclusions": ["drevesin", "po-metall", "fasad"]},
        {"name": "Грунтовка", "slug": "primer", "category": "paint", "unit": "л", "consumption_per_m2": 0.12, "waste_factor": 1.1, "package_size": 10, "layers": 1, "finish_key": "primer", "variant_tier": "avg"},
        {"name": "Шпаклевка стартовая", "slug": "putty_start", "category": "paint", "unit": "кг", "consumption_per_m2": 5.0, "waste_factor": 1.1, "package_size": 30, "finish_key": "putty_start", "variant_tier": "avg"},
        {"name": "Шпаклевка финишная", "slug": "putty_finish", "category": "paint", "unit": "кг", "consumption_per_m2": 1.0, "waste_factor": 1.1, "package_size": 25, "finish_key": "putty_finish", "variant_tier": "avg"},
        {"name": "Ламинат", "slug": "laminate", "category": "floor", "unit": "м²", "consumption_per_m2": 1.0, "waste_factor": 1.15, "package_size": 2.0, "finish_key": "floor.laminate", "variant_tier": "avg"},
        {"name": "Плинтус", "slug": "plinth", "category": "floor", "unit": "м", "consumption_per_m2": 1.0, "waste_factor": 1.05, "package_size": 1.0, "finish_key": "plinth", "variant_tier": "avg"},
        {"name": "Плитка", "slug": "tile", "category": "tile", "unit": "м²", "consumption_per_m2": 1.0, "waste_factor": 1.15, "package_size": 1.2, "finish_key": "tile", "variant_tier": "avg"},
        {"name": "Плиточный клей", "slug": "tile_adhesive", "category": "tile", "unit": "кг", "consumption_per_m2": 4.5, "waste_factor": 1.1, "package_size": 25},
        {"name": "Затирка", "slug": "grout", "category": "tile", "unit": "кг", "consumption_per_m2": 0.4, "waste_factor": 1.1, "package_size": 2},
        {"name": "Обои", "slug": "wallpaper", "category": "wall", "unit": "рулон", "consumption_per_m2": 0.2, "waste_factor": 1.1, "package_size": 1, "pattern_factor": 1.3, "finish_key": "walls.wallpaper", "variant_tier": "avg"},
        {"name": "Линолеум", "slug": "linoleum", "category": "floor", "unit": "м²", "consumption_per_m2": 1.0, "waste_factor": 1.05, "package_size": 1.0},
        {"name": "Паркетная доска", "slug": "parquet", "category": "floor", "unit": "м²", "consumption_per_m2": 1.0, "waste_factor": 1.15, "package_size": 2.0},
        {"name": "Краска влагостойкая", "slug": "paint_moisture", "category": "paint", "unit": "л", "consumption_per_m2": 0.13, "waste_factor": 1.1, "package_size": 9, "layers": 2},
        # Инженерка (works.electric / works.plumbing) — количество из запроса, не по норме.
        {"name": "Кабель электрический", "slug": "cable", "category": "electric", "unit": "м", "waste_factor": 1.1, "package_size": 1.0},
        {"name": "Розетка", "slug": "socket", "category": "electric", "unit": "шт", "package_size": 1, "finish_key": "socket", "variant_tier": "avg"},
        {"name": "Светильник", "slug": "light", "category": "electric", "unit": "шт", "package_size": 1},
        {"name": "Труба водопроводная", "slug": "pipe", "category": "plumbing", "unit": "м", "waste_factor": 1.1, "package_size": 2.0},
    ]
    for m in materials_data:
        mat = Material(**m)
        session.add(mat)
    session.flush()

    for mat in session.query(Material).all():
        mp = MaterialPrice(material_id=mat.id, source_id=src.id, price_min=100, price_avg=120, price_max=140)
        session.add(mp)

    # Варианты floor.laminate по уровню комплектации (#331) — для тестов резолва
    # SKU по (finish_key, tier) и его fallback. ceiling.paint/socket намеренно
    # остаются БЕЗ min/max-варианта (только avg выше) — на них тестируется
    # fallback на ближайший уровень.
    variant_materials = [
        Material(
            name="Ламинат эконом", slug="laminate_economy", category="floor", unit="м²",
            consumption_per_m2=1.0, waste_factor=1.15, package_size=1.5,
            finish_key="floor.laminate", variant_tier="min",
        ),
        Material(
            name="Ламинат премиум", slug="laminate_premium", category="floor", unit="м²",
            consumption_per_m2=1.0, waste_factor=1.15, package_size=2.5,
            finish_key="floor.laminate", variant_tier="max",
        ),
    ]
    for mat in variant_materials:
        session.add(mat)
    session.flush()
    session.add(MaterialPrice(
        material_id=variant_materials[0].id, source_id=src.id,
        price_min=350, price_avg=450, price_max=600,
    ))
    session.add(MaterialPrice(
        material_id=variant_materials[1].id, source_id=src.id,
        price_min=2200, price_avg=3200, price_max=4500,
    ))

    # Варианты primer (#390) — в отличие от ламината, у грунта на unit="л" висит
    # модификатор двойного слоя (primer_two_coats, см. quantity_of), матчащийся по
    # finish_key. Даёт regression-покрытие: эконом/премиум SKU (свой slug) должны
    # получать двойной слой так же, как и avg-товар.
    primer_variants = [
        Material(
            name="Грунтовка эконом", slug="primer_economy", category="paint", unit="л",
            consumption_per_m2=0.12, waste_factor=1.1, package_size=5, layers=1,
            finish_key="primer", variant_tier="min",
        ),
        Material(
            name="Грунтовка премиум", slug="primer_premium", category="paint", unit="л",
            consumption_per_m2=0.12, waste_factor=1.1, package_size=10, layers=1,
            finish_key="primer", variant_tier="max",
        ),
    ]
    for mat in primer_variants:
        session.add(mat)
    session.flush()
    session.add(MaterialPrice(
        material_id=primer_variants[0].id, source_id=src.id,
        price_min=45, price_avg=65, price_max=90,
    ))
    session.add(MaterialPrice(
        material_id=primer_variants[1].id, source_id=src.id,
        price_min=300, price_avg=450, price_max=650,
    ))

    # Региональная seed-цена для теста регионального lookup (#127):
    # отличается от базовой (avg 200 против 120), чтобы выбор региона был заметен.
    paint = session.query(Material).filter(Material.name == "Краска для стен").first()
    session.add(MaterialPrice(
        material_id=paint.id, source_id=src.id,
        price_min=180, price_avg=200, price_max=240, region="Москва",
    ))

    # Услуги. slug — как в seed_data/labor_services.json (#278).
    services_data = [
        {"name": "Покраска стен", "slug": "paint_walls", "specialist_type": "Маляр", "unit": "м²"},
        {"name": "Шпаклевка стен", "slug": "putty_walls", "specialist_type": "Маляр", "unit": "м²"},
        {"name": "Покраска потолка", "slug": "paint_ceiling", "specialist_type": "Маляр", "unit": "м²"},
        {"name": "Поклейка обоев", "slug": "wallpaper_gluing", "specialist_type": "Маляр", "unit": "м²"},
        {"name": "Укладка ламината", "slug": "lay_laminate", "specialist_type": "Укладчик", "unit": "м²"},
        {"name": "Укладка линолеума", "slug": "lay_linoleum", "specialist_type": "Укладчик", "unit": "м²"},
        {"name": "Укладка паркета", "slug": "lay_parquet", "specialist_type": "Паркетчик", "unit": "м²"},
        {"name": "Укладка плитки", "slug": "lay_tile", "specialist_type": "Плиточник", "unit": "м²"},
        {"name": "Монтаж натяжного потолка", "slug": "stretch_ceiling", "specialist_type": "Потолочник", "unit": "м²"},
        # Натяжной потолок блоком + откосы (#191).
        {"name": "Закладная под светильник", "slug": "ceiling_embed", "specialist_type": "Потолочник", "unit": "шт"},
        {"name": "Ниша под карниз", "slug": "curtain_niche", "specialist_type": "Потолочник", "unit": "м"},
        {"name": "Отделка откосов", "slug": "otkos", "specialist_type": "Штукатур", "unit": "м²"},
        {"name": "Электромонтаж", "slug": "electrical_install", "specialist_type": "Электрик", "unit": "точка"},
        {"name": "Штробление", "slug": "chasing", "specialist_type": "Электрик", "unit": "м"},
        # Сантехника (#401): установка по типу прибора вместо одной широкой услуги.
        {"name": "Установка смесителя", "slug": "install_faucet", "specialist_type": "Сантехник", "unit": "точка"},
        {"name": "Установка унитаза", "slug": "install_toilet", "specialist_type": "Сантехник", "unit": "точка"},
        {"name": "Установка бачка унитаза", "slug": "install_toilet_tank", "specialist_type": "Сантехник", "unit": "точка"},
        # Гранулярная инженерка works (#222).
        {"name": "Прокладка кабеля", "slug": "cable_lay", "specialist_type": "Электрик", "unit": "м"},
        {"name": "Монтаж розетки", "slug": "socket_mount", "specialist_type": "Электрик", "unit": "шт"},
        {"name": "Монтаж светильника", "slug": "light_mount", "specialist_type": "Электрик", "unit": "шт"},
        {"name": "Монтаж труб", "slug": "pipe_mount", "specialist_type": "Сантехник", "unit": "м"},
        # Черновые работы (#190). Демонтаж (#401) — по типу операции вместо одной
        # услуги на м² вперемешку с лёгким и капитальным демонтажом.
        {"name": "Демонтаж напольного покрытия", "slug": "demolition_floor_covering", "specialist_type": "Разнорабочий", "unit": "м²"},
        {"name": "Демонтаж стен и перегородок", "slug": "demolition_walls", "specialist_type": "Разнорабочий", "unit": "м²"},
        {"name": "Демонтаж стяжки", "slug": "demolition_screed", "specialist_type": "Разнорабочий", "unit": "м²"},
        {"name": "Выравнивание стен", "slug": "level_walls", "specialist_type": "Штукатур", "unit": "м²"},
        {"name": "Стяжка пола", "slug": "screed_floor", "specialist_type": "Стяжечник", "unit": "м²"},
        {"name": "Гидроизоляция", "slug": "waterproof", "specialist_type": "Гидроизолировщик", "unit": "м²"},
        {"name": "Грунтование", "slug": "priming", "specialist_type": "Маляр", "unit": "м²"},
        # Подготовка потолка под покраску (#380), по аналогии со стенами.
        {"name": "Грунтование потолка", "slug": "priming_ceiling", "specialist_type": "Маляр", "unit": "м²"},
        {"name": "Шпаклевка потолка", "slug": "putty_ceiling", "specialist_type": "Штукатур", "unit": "м²"},
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
# /api/estimates/calculate берёт цены материалов через парсеры. Чтобы тесты не
# тащили живой Мегастрой/Леман (флак на VPN/офлайн/смене вёрстки), список парсеров
# инжектится через зависимость get_material_parsers и подменяется этой заглушкой.

class _StubMaterialParser(BaseParser):
    """Заглушка парсера материалов: НЕ ходит в сеть.

    По умолчанию падает → агрегатор откатывается на seed. Можно задать callable
    fetch(material_name) -> ParsedPrice, чтобы проверить ветку «цена от парсера»."""

    source_name = "Мегастрой"

    def __init__(self, fetch=None):
        self._fetch = fetch

    def fetch_price(
        self, material_name: str, reference_package_size=None, apply_undersized_filter=True
    ) -> ParsedPrice:
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
    Подменяет ровно один источник (список из одного элемента) — этого достаточно
    для тестов, не завязанных на объединение нескольких источников (#333); для
    них см. get_material_price напрямую в test_price_normalization.py.
    Возвращает настройщик: вызови stub_material_parser(fetch) с функцией
    fetch(material_name) -> ParsedPrice, чтобы протестировать ветку парсера."""

    def _install(fetch=None):
        _clear_parser_material_prices()
        app.dependency_overrides[get_material_parsers] = lambda: [_StubMaterialParser(fetch)]

    _install()  # дефолт — падающий парсер, гарантированный seed
    yield _install
    app.dependency_overrides.pop(get_material_parsers, None)

