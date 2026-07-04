from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone

from app.db.session import SessionLocal
from app.db.models import Material, LaborService, MaterialPrice, LaborPrice, PriceSource
from app.schemas.admin import PriceUpdateRequest

router = APIRouter(prefix="/api/admin", tags=["admin"])


def get_manual_source(session) -> PriceSource:
    source = session.query(PriceSource).filter(PriceSource.name == "manual").first()
    if not source:
        raise HTTPException(status_code=500, detail="Manual price source not found in DB")
    return source


def _upsert_manual_price(session, price_model, entity_model, fk_field: str, entity_id: int, body: PriceUpdateRequest):
    """Get-or-create manual-цены для материала/работы.

    Проверяем существование сущности → иначе 404 (без этого создавалась запись
    с битым FK и commit падал необработанным 500). Затем обновляем существующую
    manual-цену или создаём новую. Возвращает сохранённую строку цены."""
    if session.get(entity_model, entity_id) is None:
        raise HTTPException(status_code=404, detail=f"{entity_model.__name__} {entity_id} not found")

    source = get_manual_source(session)

    price = session.query(price_model).filter(
        getattr(price_model, fk_field) == entity_id,
        price_model.source_id == source.id,
    ).first()

    if price is None:
        price = price_model(**{fk_field: entity_id}, source_id=source.id)
        session.add(price)

    price.price_min = body.price_min
    price.price_avg = body.price_avg
    price.price_max = body.price_max
    # region обновляем только если он явно прислан — иначе PATCH без region затирал бы
    # существующее значение в None (частичное обновление, а не полная замена строки).
    if "region" in body.model_fields_set:
        price.region = body.region
    price.updated_at = datetime.now(timezone.utc)

    session.commit()
    session.refresh(price)
    return price


@router.patch("/material-prices/{material_id}")
def update_material_price(material_id: int, body: PriceUpdateRequest):
    session = SessionLocal()
    try:
        price = _upsert_manual_price(session, MaterialPrice, Material, "material_id", material_id, body)
        return {
            "material_id": material_id,
            "source": "manual",
            "price_min": price.price_min,
            "price_avg": price.price_avg,
            "price_max": price.price_max,
            "updated_at": price.updated_at,
        }
    finally:
        session.close()


@router.patch("/labor-prices/{labor_service_id}")
def update_labor_price(labor_service_id: int, body: PriceUpdateRequest):
    session = SessionLocal()
    try:
        price = _upsert_manual_price(session, LaborPrice, LaborService, "labor_service_id", labor_service_id, body)
        return {
            "labor_service_id": labor_service_id,
            "source": "manual",
            "price_min": price.price_min,
            "price_avg": price.price_avg,
            "price_max": price.price_max,
            "updated_at": price.updated_at,
        }
    finally:
        session.close()
