import json
from pathlib import Path

from app.db.session import SessionLocal
from app.db.models import Material, PriceSource, LaborService, MaterialPrice, LaborPrice, RoomType

from decimal import Decimal

SEED_PATH = Path(__file__).resolve().parent / "seed_data"


def _load_seed_data() -> dict:
    """Читает все seed_data/*.json одним словарём (общий вход для seed и дозасева)."""
    def _read(name: str, encoding: str | None = None):
        with open(SEED_PATH / name, "r", encoding=encoding) as file:
            return json.load(file)

    return {
        "materials": _read("materials.json"),
        "sources": _read("price_sources.json"),
        "services": _read("labor_services.json"),
        "material_prices": _read("material_prices.json"),
        "labor_prices": _read("labor_prices.json"),
        "room_types": _read("room_types.json", encoding="utf-8"),
    }


def seed():
    loaded = _load_seed_data()
    data = loaded["materials"]
    data_sources = loaded["sources"]
    data_services = loaded["services"]
    data_material_prices = loaded["material_prices"]
    data_labor_prices = loaded["labor_prices"]
    data_room_types = loaded["room_types"]

    session = SessionLocal()
    session.query(RoomType).delete()
    # сначала дети (цены) — на них ничего не ссылается
    session.query(MaterialPrice).delete()
    session.query(LaborPrice).delete()
    # потом родители
    session.query(Material).delete()
    session.query(LaborService).delete()
    session.query(PriceSource).delete()

    materials = []
    for item in data:
        material = Material(**item)
        materials.append(material)

    session.add_all(materials)

    price_sources = []
    for item in data_sources:
        price = PriceSource(**item)
        price_sources.append(price)
    
    session.add_all(price_sources)

    labor_services = []
    for item in data_services:
        labor = LaborService(**item)
        labor_services.append(labor)
    
    session.add_all(labor_services)

    session.flush()
    materials_by_name = {m.name: m for m in materials}
    sources_by_name = {s.name: s for s in price_sources}
    services_by_name = {sv.name: sv for sv in labor_services}

    material_prices = []
    for item in data_material_prices:
        material = materials_by_name[item["material"]]   # находим объект по имени
        source = sources_by_name[item["source"]]
        price = MaterialPrice(
            material_id=material.id,                      # реальный id после flush
            source_id=source.id,
            price_min=Decimal(item["price_min"]),         # строка - Decimal
            price_avg=Decimal(item["price_avg"]),
            price_max=Decimal(item["price_max"]),
            region=item.get("region"),                    # .get() вернёт None, если ключа нет
        )
        material_prices.append(price)

    session.add_all(material_prices)

    labor_prices = []
    for item in data_labor_prices:
        service = services_by_name[item["service"]]   # находим объект по имени
        source = sources_by_name[item["source"]]
        price = LaborPrice(
            labor_service_id=service.id,                      # реальный id после flush
            source_id=source.id,
            price_min=Decimal(item["price_min"]),         # строка - Decimal
            price_avg=Decimal(item["price_avg"]),
            price_max=Decimal(item["price_max"]),
            region=item.get("region"),                    # .get() вернёт None, если ключа нет
        )
        labor_prices.append(price)

    session.add_all(labor_prices)

    room_types = []
    for key, rules in data_room_types["roomTypes"].items():
        room_types.append(RoomType(
            key=key,
            label=rules["label"],
            rules=rules,            # кладем весь объект как JSONB
        ))
    session.add_all(room_types)

    session.commit()
    session.close()


def seed_missing() -> dict:
    """Идемпотентный дозасев: добавляет недостающие справочники и seed-цены,
    НИЧЕГО не удаляя.

    В отличие от seed() (полный wipe-and-reseed, затирающий кэш парсеров),
    здесь INSERT только того, чего в БД ещё нет:
    - источники/материалы/услуги, которых нет по name;
    - seed-цены — ТОЛЬКО для материалов/услуг, у которых цен ещё нет.
    Существующие цены (в т.ч. собранные парсерами через update_prices) не трогаются.
    Возвращает счётчик добавленного. Безопасно запускать повторно.
    """
    loaded = _load_seed_data()
    session = SessionLocal()
    added = {
        "sources": 0, "materials": 0, "services": 0,
        "material_prices": 0, "labor_prices": 0,
    }
    try:
        existing_sources = {s.name for s in session.query(PriceSource).all()}
        for item in loaded["sources"]:
            if item["name"] not in existing_sources:
                session.add(PriceSource(**item))
                added["sources"] += 1

        existing_materials = {m.name for m in session.query(Material).all()}
        for item in loaded["materials"]:
            if item["name"] not in existing_materials:
                session.add(Material(**item))
                added["materials"] += 1

        existing_services = {s.name for s in session.query(LaborService).all()}
        for item in loaded["services"]:
            if item["name"] not in existing_services:
                session.add(LaborService(**item))
                added["services"] += 1

        session.flush()

        materials_by_name = {m.name: m for m in session.query(Material).all()}
        services_by_name = {s.name: s for s in session.query(LaborService).all()}
        sources_by_name = {s.name: s for s in session.query(PriceSource).all()}

        # Цены добавляем только позициям без цен — чтобы не плодить дубли seed-строк
        # у материалов/услуг, где уже есть цены (в т.ч. от парсеров).
        priced_materials = {
            mid for (mid,) in session.query(MaterialPrice.material_id).distinct()
        }
        for item in loaded["material_prices"]:
            material = materials_by_name[item["material"]]
            if material.id in priced_materials:
                continue
            session.add(MaterialPrice(
                material_id=material.id,
                source_id=sources_by_name[item["source"]].id,
                price_min=Decimal(item["price_min"]),
                price_avg=Decimal(item["price_avg"]),
                price_max=Decimal(item["price_max"]),
                region=item.get("region"),
            ))
            added["material_prices"] += 1

        priced_services = {
            sid for (sid,) in session.query(LaborPrice.labor_service_id).distinct()
        }
        for item in loaded["labor_prices"]:
            service = services_by_name[item["service"]]
            if service.id in priced_services:
                continue
            session.add(LaborPrice(
                labor_service_id=service.id,
                source_id=sources_by_name[item["source"]].id,
                price_min=Decimal(item["price_min"]),
                price_avg=Decimal(item["price_avg"]),
                price_max=Decimal(item["price_max"]),
                region=item.get("region"),
            ))
            added["labor_prices"] += 1

        session.commit()
    finally:
        session.close()

    return added


def _already_seeded() -> bool:
    """Есть ли уже справочные данные (значит, БД не пустая)."""
    session = SessionLocal()
    try:
        return session.query(Material.id).first() is not None
    finally:
        session.close()


if __name__ == "__main__":
    import sys

    # --missing: идемпотентный дозасев непустой БД (добавить новые позиции
    # из seed_data, не трогая существующие цены). Безопасен на проде — не
    # затирает кэш парсеров. Именно этот режим применяет новые материалы/
    # услуги после мёржа в seed без полного wipe-and-reseed.
    if "--missing" in sys.argv:
        added = seed_missing()
        print(f"Seed (дозасев): добавлено {added}.")
    # --if-empty: режим деплоя — засеять только пустую БД и не перетирать
    # данные (в т.ч. правки цен) при каждом рестарте контейнера.
    # Без флага (тесты/dev) seed всегда делает полный сброс, как и раньше.
    elif "--if-empty" in sys.argv and _already_seeded():
        print("Seed: данные уже есть, пропускаю (--if-empty).")
    else:
        seed()