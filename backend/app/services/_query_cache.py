"""Мемоизация запросов к статическим справочникам в пределах одной сессии.

Кэш живёт на ``session.info`` — то есть ровно на времени жизни конкретной Session:
в проде это сессия одного HTTP-запроса (Depends(get_db)), в CLI/тестах — своя
SessionLocal(). Поэтому между запросами кэш не протекает, а внутри запроса убирает
N+1 по справочникам, которые расчёт сметы дёргает по имени/slug десятки раз
(PriceSource "seed" и источники парсеров, Material/LaborService по имени).

Кэшируем ТОЛЬКО статические справочники, которые в ходе запроса не создаются и не
переименовываются. Изменяемые строки цен (MaterialPrice/LaborPrice) сюда не кладём —
их get_price может обновлять и коммитить. Негативный результат (None — записи нет)
кэшируется тоже: в пределах запроса он не изменится.
"""
from sqlalchemy.orm import Session

from app.db.models import LaborService, Material, PriceSource


def _bucket(db: Session, name: str) -> dict:
    return db.info.setdefault(name, {})


def source_by_name(db: Session, name: str) -> PriceSource | None:
    cache = _bucket(db, "_cache_source_by_name")
    if name not in cache:
        cache[name] = db.query(PriceSource).filter(PriceSource.name == name).first()
    return cache[name]


def source_name_by_id(db: Session, source_id: int) -> str | None:
    cache = _bucket(db, "_cache_source_name_by_id")
    if source_id not in cache:
        src = db.query(PriceSource).filter(PriceSource.id == source_id).first()
        cache[source_id] = src.name if src else None
    return cache[source_id]


def material_by_name(db: Session, name: str) -> Material | None:
    cache = _bucket(db, "_cache_material_by_name")
    if name not in cache:
        cache[name] = db.query(Material).filter(Material.name == name).first()
    return cache[name]


def labor_service_by_name(db: Session, name: str) -> LaborService | None:
    cache = _bucket(db, "_cache_labor_service_by_name")
    if name not in cache:
        cache[name] = db.query(LaborService).filter(LaborService.name == name).first()
    return cache[name]


def material_by_slug(db: Session, slug: str) -> Material | None:
    cache = _bucket(db, "_cache_material_by_slug")
    if slug not in cache:
        cache[slug] = db.query(Material).filter(Material.slug == slug).first()
    return cache[slug]


def material_variants_by_finish_key(db: Session, finish_key: str) -> list[Material]:
    cache = _bucket(db, "_cache_material_variants")
    if finish_key not in cache:
        cache[finish_key] = (
            db.query(Material).filter(Material.finish_key == finish_key).all()
        )
    return cache[finish_key]


def labor_service_by_slug(db: Session, slug: str) -> LaborService | None:
    cache = _bucket(db, "_cache_labor_service_by_slug")
    if slug not in cache:
        cache[slug] = db.query(LaborService).filter(LaborService.slug == slug).first()
    return cache[slug]
