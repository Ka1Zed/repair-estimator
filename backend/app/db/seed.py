import json
from pathlib import Path

from app.db.session import SessionLocal
from app.db.models import Material, PriceSource, LaborService, MaterialPrice, LaborPrice

from decimal import Decimal

def seed():
    SEED_PATH = Path(__file__).resolve().parent / "seed_data"

    with open(SEED_PATH / "materials.json", 'r') as file:
        data = json.load(file)

    with open(SEED_PATH / "price_sources.json", 'r') as file:
        data_sources = json.load(file)

    with open(SEED_PATH / "labor_services.json", 'r') as file:
        data_services = json.load(file)

    with open(SEED_PATH / "material_prices.json", 'r') as file:
        data_material_prices = json.load(file)
    
    with open(SEED_PATH / "labor_prices.json", 'r') as file:
        data_labor_prices = json.load(file)

    session = SessionLocal()
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

    session.commit()
    session.close()

if __name__ == "__main__":
    seed()