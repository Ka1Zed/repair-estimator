# app/services/hidden_works_service.py
#
# Блок «может всплыть доплатой» (#239).
#
# Скрытые работы — типовые сюрпризы, которые вскрываются только на объекте
# (непредвиденный демонтаж, замена старой стяжки, штробы в бетоне под кабель,
# доп. выравнивание кривых стен, старая гидроизоляция под замену). Их нельзя
# зашить в основную смету (заранее не оценить), но нельзя и молчать — поэтому
# отдаём отдельным блоком с ОРИЕНТИРОВОЧНОЙ вилкой, НЕ входящей в summary.
#
# Правила состава и трактовку блока см. docs/estimation-rules.md, раздел
# «Скрытые работы». Цены за единицу берём из seed-работ (get_labor_price),
# объёмы — из геометрии сценария; класс/непредвиденные (CONTINGENCY) здесь НЕ
# применяем — это отдельный справочный риск, а не строка итоговой сметы.

from decimal import Decimal
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.db.models import LaborService
from app.services._num import D as _D
from app.services.price_aggregator_service import get_labor_price

NOTE = (
    "Ориентировочная вилка возможных доплат за скрытые работы. НЕ входит в "
    "итоговую смету (summary) — всплывает только при вскрытии конструкций. "
    "Объёмы и цены приблизительные."
)

# Slug операций (как в seed_data/labor_services.json, поле slug) — цену берём
# по ним, name — только человекочитаемый label для API-ответа (#278).
# Демонтаж разбит по типу операции (#401) — берём demolition_floor_covering как
# единственную подуслугу, актуальную в любой комнате (см. labor_calc_service.py,
# тот же выбор для симметричной строки в calculate_rough_labor).
_S_DEMOLITION = "demolition_floor_covering"
_S_SCREED = "screed_floor"
_S_LEVEL_WALLS = "level_walls"
_S_CHASING = "chasing"
_S_WATERPROOF = "waterproof"


def _source_name(source_id, sources_by_id: Dict[int, str] | None) -> str:
    if not source_id or not sources_by_id:
        return "seed"
    return sources_by_id.get(source_id, "seed")


def _service_row(db: Session, service_slug: str):
    return db.query(LaborService).filter(LaborService.slug == service_slug).first()


def _priced_item(
    service_slug: str, reason: str, volume: Decimal, city: str, db: Session,
    sources_by_id: Dict[int, str] | None = None,
):
    """Одна строка скрытых работ; None, если объём нулевой, услуга не засидована
    или нет seed-цены."""
    volume = _D(volume)
    if volume <= 0:
        return None
    svc_row = _service_row(db, service_slug)
    if svc_row is None:
        return None  # услуга не засидована — молча пропускаем строку
    # get_labor_price матчит по name (граница с парсерами работ, см. #278) —
    # берём человекочитаемое имя из уже найденной по slug строки.
    price = get_labor_price(svc_row.name, db=db, region=city)
    if price is None:
        return None  # цена не засидована — молча пропускаем строку
    p_min, p_avg, p_max = _D(price.price_min), _D(price.price_avg), _D(price.price_max)
    return {
        "service": svc_row.name,
        "specialist": svc_row.specialist_type,
        "reason": reason,
        "volume": float(volume),
        "unit": svc_row.unit,
        "price_avg": float(p_avg),
        "total_min": float(volume * p_min),
        "total_avg": float(volume * p_avg),
        "total_max": float(volume * p_max),
        "source": _source_name(price.source_id, sources_by_id),
    }


def calculate_hidden_works(
    *,
    floor_area: Decimal,
    wall_area: Decimal,
    cable_m: Decimal,
    has_floor: bool,
    has_walls: bool,
    has_electric: bool,
    wet_floor_area: Decimal,
    city: str,
    db: Session,
    sources_by_id: Dict[int, str] | None = None,
) -> Dict[str, Any]:
    """Блок скрытых работ по сценарию (#239). Всегда возвращает note + items (может быть пуст).

    Состав (см. docs/estimation-rules.md):
      - демонтаж скрытых слоёв — всегда (есть комнаты → есть что вскрывать);
      - замена стяжки — если выбрана отделка пола;
      - доп. выравнивание стен — если выбрана отделка стен;
      - штробление в бетоне — если включена электрика (по метражу кабеля);
      - гидроизоляция — по площади пола мокрых комнат (сантехника/санузел).

    Суммы блока (total_*) справочные и НЕ входят в summary основной сметы.
    """
    candidates = [
        (True, _S_DEMOLITION,
         "Под старой отделкой могут открыться слои под доп. демонтаж", floor_area),
        (has_floor, _S_SCREED,
         "Старая стяжка бывает в трещинах/с перепадами — возможна частичная замена", floor_area),
        (has_walls, _S_LEVEL_WALLS,
         "Реальная кривизна стен вскрывается после демонтажа — возможен доп. слой", wall_area),
        (has_electric, _S_CHASING,
         "Штробы под кабель в бетоне/кирпиче — объём ясен только на месте", cable_m),
        (wet_floor_area > 0, _S_WATERPROOF,
         "Старая/повреждённая гидроизоляция под замену в мокрой зоне", wet_floor_area),
    ]

    items: List[Dict[str, Any]] = []
    totals = {"min": Decimal(0), "avg": Decimal(0), "max": Decimal(0)}
    for applies, service, reason, volume in candidates:
        if not applies:
            continue
        item = _priced_item(service, reason, volume, city, db, sources_by_id=sources_by_id)
        if item is None:
            continue
        items.append(item)
        totals["min"] += _D(item["total_min"])
        totals["avg"] += _D(item["total_avg"])
        totals["max"] += _D(item["total_max"])

    return {
        "note": NOTE,
        "total_min": float(totals["min"]),
        "total_avg": float(totals["avg"]),
        "total_max": float(totals["max"]),
        "items": items,
    }
