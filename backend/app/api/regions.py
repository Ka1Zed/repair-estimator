from fastapi import APIRouter

from app.db.session import SessionLocal
from app.db.models import MaterialPrice, LaborPrice

router = APIRouter(prefix="/api", tags=["regions"])

# Город по умолчанию: для него и для любого города без своих цен расчёт идёт
# по базовым seed-ценам (region IS NULL).
DEFAULT_REGION = "Казань"


@router.get("/regions")
def get_regions():
    '''
    Справочник доступных городов для селектора на странице сметы.

    Возвращает distinct непустые region из ценовых таблиц плюс город по умолчанию,
    чтобы он всегда присутствовал в списке, даже если своих строк цен у него ещё нет.
    '''
    session = SessionLocal()
    try:
        material_regions = session.query(MaterialPrice.region).distinct().all()
        labor_regions = session.query(LaborPrice.region).distinct().all()
    finally:
        session.close()

    regions = {r[0] for r in material_regions + labor_regions if r[0]}
    regions.add(DEFAULT_REGION)

    return {
        "default": DEFAULT_REGION,
        "regions": sorted(regions),
    }
