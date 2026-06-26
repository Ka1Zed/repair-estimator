import logging
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.db.session import SessionLocal
from app.db.models import Material, MaterialPrice, PriceSource, LaborService, LaborPrice
from app.parsers.base import BaseParser

logger = logging.getLogger(__name__)


def _is_fresh(updated_at: datetime | None, ttl_hours: int) -> bool:
    '''Цена считается актуальной, если её обновляли позже, чем ttl_hours назад.'''
    if updated_at is None:
        return False
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - updated_at < timedelta(hours=ttl_hours)


def get_price(
    material_name: str,
    parser: BaseParser | None = None,
    region: str | None = None,
    ttl_hours: int | None = None,
    force_refresh: bool = False,
) -> MaterialPrice | None:
    '''
    Возвращает актуальную цену для материала.

    Логика (TTL-кэш, чтобы расчёт сметы не ходил в интернет на каждый запрос):
    1. Если есть свежая (моложе ttl_hours) цена парсера в БД — возвращаем её, не трогая сайт.
    2. Иначе, если передан парсер — пробуем спарсить и сохранить свежую цену.
    3. Если парсер упал/не передан/нет источника — берём seed-цену из БД.
       При заданном region сначала ищем seed-цену этого региона, при отсутствии —
       базовую seed-цену с region IS NULL. Парсер региону не подчиняется (одна цена на всех).
    4. force_refresh=True заставляет дёрнуть парсер даже при свежем кэше (для CLI update_prices).
    5. Наверх исключение не пробрасываем никогда.
    '''
    if ttl_hours is None:
        ttl_hours = settings.PRICE_TTL_HOURS

    session = SessionLocal()
    try:
        material = session.query(Material).filter(Material.name == material_name).first()
        if not material:
            logger.warning(f"Материал '{material_name}' не найден в БД")
            return None

        # Пробуем парсер
        if parser is not None:
            source = session.query(PriceSource).filter(
                PriceSource.name == parser.source_name
            ).first()

            price_entry = None
            if source:
                price_entry = session.query(MaterialPrice).filter(
                    MaterialPrice.material_id == material.id,
                    MaterialPrice.source_id == source.id
                ).first()

            # Свежий кэш парсера — отдаём без сетевого запроса
            if not force_refresh and price_entry and _is_fresh(price_entry.updated_at, ttl_hours):
                logger.info(f"Цена для '{material_name}' взята из кэша {parser.source_name}")
                return price_entry

            try:
                parsed = parser.fetch_price(material_name)

                if source:
                    if price_entry:
                        # Обновляем
                        price_entry.price_min = parsed.price_min
                        price_entry.price_avg = parsed.price_avg
                        price_entry.price_max = parsed.price_max
                        price_entry.updated_at = datetime.now(timezone.utc)
                    else:
                        # Создаем новую
                        price_entry = MaterialPrice(
                            material_id=material.id,
                            source_id=source.id,
                            price_min=parsed.price_min,
                            price_avg=parsed.price_avg,
                            price_max=parsed.price_max,
                            updated_at=datetime.now(timezone.utc)
                        )
                        session.add(price_entry)

                    session.commit()
                    session.refresh(price_entry)
                    logger.info(f"Цена для '{material_name}' получена от парсера {parser.source_name}")
                    return price_entry

            except Exception as e:
                # Парсер упал - логируем и идем в fallback
                logger.warning(f"Парсер {parser.source_name} не смог получить цену для '{material_name}': {e}")

        # Fallback: берем seed-цену из БД
        seed_source = session.query(PriceSource).filter(PriceSource.name == "seed").first()
        if not seed_source:
            logger.error("Источник 'seed' не найден в БД")
            return None

        seed_price = None
        if region is not None:
            # Региональная seed-цена имеет приоритет над базовой.
            seed_price = session.query(MaterialPrice).filter(
                MaterialPrice.material_id == material.id,
                MaterialPrice.source_id == seed_source.id,
                MaterialPrice.region == region,
            ).first()

        if seed_price is None:
            # Базовая seed-цена (region IS NULL) — fallback по умолчанию.
            seed_price = session.query(MaterialPrice).filter(
                MaterialPrice.material_id == material.id,
                MaterialPrice.source_id == seed_source.id,
                MaterialPrice.region.is_(None),
            ).first()

        if seed_price:
            logger.info(f"Цена для '{material_name}' взята из seed (fallback), region={region}")
        else:
            logger.warning(f"Seed-цена для '{material_name}' не найдена")

        return seed_price

    finally:
        session.close()


def get_labor_price(service_name: str, region: str | None = None) -> LaborPrice | None:
    '''
    Возвращает seed-цену работы с учётом региона.

    При заданном region сначала ищем seed-цену этого региона, при отсутствии —
    базовую seed-цену с region IS NULL. Исключение наверх не пробрасываем.
    '''
    session = SessionLocal()
    try:
        service = session.query(LaborService).filter(LaborService.name == service_name).first()
        if not service:
            logger.warning(f"Услуга '{service_name}' не найдена в БД")
            return None

        seed_source = session.query(PriceSource).filter(PriceSource.name == "seed").first()
        if not seed_source:
            logger.error("Источник 'seed' не найден в БД")
            return None

        price = None
        if region is not None:
            price = session.query(LaborPrice).filter(
                LaborPrice.labor_service_id == service.id,
                LaborPrice.source_id == seed_source.id,
                LaborPrice.region == region,
            ).first()

        if price is None:
            price = session.query(LaborPrice).filter(
                LaborPrice.labor_service_id == service.id,
                LaborPrice.source_id == seed_source.id,
                LaborPrice.region.is_(None),
            ).first()

        if price:
            logger.info(f"Цена работы '{service_name}' взята из seed, region={region}")
        else:
            logger.warning(f"Seed-цена для работы '{service_name}' не найдена")

        return price
    finally:
        session.close()


def update_labor_price(service_name: str, parser) -> LaborPrice | None:
    '''
    Берет цену услуги через парсер и пишет в labor_prices с источником парсера
    При любой ошибке парсера — ничего не меняет, возвращает None (старые цены остаются)
    '''
    session = SessionLocal()
    try:
        service = session.query(LaborService).filter(LaborService.name == service_name).first()
        if not service:
            logger.warning(f"Услуга '{service_name}' не найдена в БД")
            return None

        try:
            parsed = parser.fetch_price(service_name)
        except Exception as e:
            logger.warning(f"Парсер {parser.source_name} не смог получить цену для '{service_name}': {e}")
            return None

        source = session.query(PriceSource).filter(PriceSource.name == parser.source_name).first()
        if not source:
            logger.error(f"Источник '{parser.source_name}' не найден в БД")
            return None

        price = session.query(LaborPrice).filter(
            LaborPrice.labor_service_id == service.id,
            LaborPrice.source_id == source.id
        ).first()
        if not price:
            price = LaborPrice(labor_service_id=service.id, source_id=source.id)
            session.add(price)

        price.price_min = parsed.price_min
        price.price_avg = parsed.price_avg
        price.price_max = parsed.price_max
        price.updated_at = datetime.now(timezone.utc)

        session.commit()
        session.refresh(price)
        logger.info(f"Цена услуги '{service_name}' обновлена от {parser.source_name}")
        return price
    finally:
        session.close()