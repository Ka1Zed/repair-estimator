from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.regions import DEFAULT_REGION
from app.db.session import get_db
from app.db.models import MaterialPrice, LaborPrice
from app.parsers.base import BaseParser
from app.services.price_aggregator_service import get_available_stores
from app.api.estimates import get_material_parsers

router = APIRouter(prefix="/api", tags=["regions"])


@router.get("/regions")
def get_regions(db: Session = Depends(get_db)):
    '''
    Справочник доступных городов для селектора на странице сметы.

    Возвращает distinct непустые region из ценовых таблиц плюс город по умолчанию,
    чтобы он всегда присутствовал в списке, даже если своих строк цен у него ещё нет.
    '''
    material_regions = db.query(MaterialPrice.region).distinct().all()
    labor_regions = db.query(LaborPrice.region).distinct().all()

    regions = {r[0] for r in material_regions + labor_regions if r[0]}
    regions.add(DEFAULT_REGION)

    return {
        "default": DEFAULT_REGION,
        "regions": sorted(regions),
    }


@router.get("/regions/stores")
def get_store_availability(city: str, parsers: list[BaseParser] = Depends(get_material_parsers)):
    '''
    Список магазинов материалов (Мегастрой/Леман) с признаком доступности для
    запрошенного города (#363) — чтобы пользователь мог явно выбрать магазин
    в /calculate, а не полагаться на скрытый автоподбор по covered_cities.

    `available: true` — магазин реально участвует в расчёте цены для этого
    города (см. price_aggregator_service.get_material_price/_select_regional_parsers);
    `available: false` — магазин известен системе, но физически не покрывает город
    (напр. Мегастрой для Москвы/СПб, где единственный источник — региональный Леман).
    '''
    return {
        "city": city,
        "stores": get_available_stores(parsers, city),
    }
