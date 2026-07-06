import json
from pathlib import Path

from sqlalchemy import func

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

    Ограничение: если у позиции уже есть хоть одна цена, новые seed-цены для неё
    не добавляются (даже если в seed_data их стало больше). Дозасев рассчитан на
    появление новых позиций, а не на доливку строк к уже ценованным.
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


def refresh_seed_prices() -> dict:
    """Доставляет пере-калиброванные seed-цены на непустую БД (#282).

    Механизм пересида: раньше на прод не было способа обновить УЖЕ засеянные
    seed-цены — `--if-empty` непустую БД не трогает, `--missing` цены не апдейтит.
    Из-за этого прод жил на ценах до рекалибровки #213 (клей 500 ₽/кг вместо 25).

    Что делает:
    - UPDATE price_min/avg/max у существующих строк с source='seed' значениями из
      seed_data/*.json (ключ строки — материал/услуга + source='seed' + region);
    - цены ДРУГИХ источников (кэш парсеров, региональные не-seed) НЕ трогает;
    - позиции/строки, которых в БД ещё нет, дозасевает как --missing (новые
      материалы/услуги/источники + недостающие seed-строки, в т.ч. новый регион).

    Возвращает счётчик: сколько справочников дозасеяно, сколько seed-строк добавлено
    и сколько обновлено. Идемпотентно: повторный прогон на тех же seed_data — no-op
    (все счётчики нулевые), updated_at не дёргается, если цена не изменилась.
    """
    # Сначала дозасев (как --missing): добавит новые материалы/услуги/источники и
    # seed-цены позиций, у которых цен ещё не было. Существующие цены не трогает —
    # их пере-калибровку делает второй проход ниже.
    added = seed_missing()
    loaded = _load_seed_data()

    session = SessionLocal()
    result = {
        "sources": added["sources"],
        "materials": added["materials"],
        "services": added["services"],
        "prices_added": added["material_prices"] + added["labor_prices"],
        "prices_updated": 0,
    }
    try:
        seed_source = session.query(PriceSource).filter_by(name="seed").first()
        if seed_source is None:
            return result  # seed-источника нет и дозасев его не создал — обновлять нечего

        def _refresh(items, price_model, owner_model, owner_fk, owner_ref):
            owners_by_name = {o.name: o for o in session.query(owner_model).all()}
            for item in items:
                owner = owners_by_name.get(item[owner_ref])
                if owner is None:
                    continue  # такого материала/услуги нет даже после дозасева — пропускаем
                new = (
                    Decimal(item["price_min"]),
                    Decimal(item["price_avg"]),
                    Decimal(item["price_max"]),
                )
                row = session.query(price_model).filter_by(
                    **{owner_fk: owner.id},
                    source_id=seed_source.id,
                    region=item.get("region"),
                ).first()
                if row is None:
                    # Строки нет (напр. новый регион у уже ценованной позиции —
                    # такую --missing пропускает) → дозасеваем недостающую seed-строку.
                    session.add(price_model(**{
                        owner_fk: owner.id,
                        "source_id": seed_source.id,
                        "price_min": new[0],
                        "price_avg": new[1],
                        "price_max": new[2],
                        "region": item.get("region"),
                    }))
                    result["prices_added"] += 1
                    continue
                if (row.price_min, row.price_avg, row.price_max) != new:
                    row.price_min, row.price_avg, row.price_max = new
                    row.updated_at = func.now()  # отметить свежесть только при реальной правке
                    result["prices_updated"] += 1

        _refresh(loaded["material_prices"], MaterialPrice, Material, "material_id", "material")
        _refresh(loaded["labor_prices"], LaborPrice, LaborService, "labor_service_id", "service")

        session.commit()
    finally:
        session.close()

    return result


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
    # --refresh-seed-prices: пере-калибровка seed-цен на непустой БД (#282).
    # UPDATE строк с source='seed' из seed_data + дозасев недостающих; кэш
    # парсеров и региональные не-seed цены не трогает. Прогонять на проде после
    # выкатки, когда seed_data/*.json изменили (напр. рекалибровка цен #213).
    elif "--refresh-seed-prices" in sys.argv:
        stats = refresh_seed_prices()
        print(f"Seed (пере-калибровка цен): {stats}.")
    # --if-empty: режим деплоя — засеять только пустую БД и не перетирать
    # данные (в т.ч. правки цен) при каждом рестарте контейнера.
    # Без флага (тесты/dev) seed всегда делает полный сброс, как и раньше.
    elif "--if-empty" in sys.argv and _already_seeded():
        print("Seed: данные уже есть, пропускаю (--if-empty).")
    else:
        seed()
