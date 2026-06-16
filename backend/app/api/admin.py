from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone

from app.db.session import SessionLocal
from app.db.models import MaterialPrice, LaborPrice, PriceSource
from app.schemas.admin import PriceUpdateRequest

router = APIRouter(prefix="/api/admin", tags=["admin"])


def get_manual_source(session) -> PriceSource:
    source = session.query(PriceSource).filter(PriceSource.name == "manual").first()
    if not source:
        raise HTTPException(status_code=500, detail="Manual price source not found in DB")
    return source


@router.patch("/material-prices/{material_id}")
def update_material_price(material_id: int, body: PriceUpdateRequest):
    session = SessionLocal()
    try:
        source = get_manual_source(session)

        price = session.query(MaterialPrice).filter(
            MaterialPrice.material_id == material_id,
            MaterialPrice.source_id == source.id
        ).first()

        if price:
            # обновляем существующую запись
            price.price_min = body.price_min
            price.price_avg = body.price_avg
            price.price_max = body.price_max
            price.region = body.region
            price.updated_at = datetime.now(timezone.utc)
        else:
            # создаём новую запись с source=manual
            price = MaterialPrice(
                material_id=material_id,
                source_id=source.id,
                price_min=body.price_min,
                price_avg=body.price_avg,
                price_max=body.price_max,
                region=body.region,
                updated_at=datetime.now(timezone.utc)
            )
            session.add(price)

        session.commit()
        session.refresh(price)
        return {
            "material_id": material_id,
            "source": "manual",
            "price_min": price.price_min,
            "price_avg": price.price_avg,
            "price_max": price.price_max,
            "updated_at": price.updated_at
        }
    finally:
        session.close()


@router.patch("/labor-prices/{labor_service_id}")
def update_labor_price(labor_service_id: int, body: PriceUpdateRequest):
    session = SessionLocal()
    try:
        source = get_manual_source(session)

        price = session.query(LaborPrice).filter(
            LaborPrice.labor_service_id == labor_service_id,
            LaborPrice.source_id == source.id
        ).first()

        if price:
            price.price_min = body.price_min
            price.price_avg = body.price_avg
            price.price_max = body.price_max
            price.region = body.region
            price.updated_at = datetime.now(timezone.utc)
        else:
            price = LaborPrice(
                labor_service_id=labor_service_id,
                source_id=source.id,
                price_min=body.price_min,
                price_avg=body.price_avg,
                price_max=body.price_max,
                region=body.region,
                updated_at=datetime.now(timezone.utc)
            )
            session.add(price)

        session.commit()
        session.refresh(price)
        return {
            "labor_service_id": labor_service_id,
            "source": "manual",
            "price_min": price.price_min,
            "price_avg": price.price_avg,
            "price_max": price.price_max,
            "updated_at": price.updated_at
        }
    finally:
        session.close()