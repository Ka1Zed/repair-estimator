# app/services/price_aggregator_service.py

import logging
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.models import Material, MaterialPrice, PriceSource, LaborService, LaborPrice
from app.parsers.base import BaseParser

logger = logging.getLogger(__name__)


def get_price(
    material_name: str,
    parser: BaseParser | None = None,
    db_session: Optional[Session] = None,   # <-- новый параметр
) -> MaterialPrice | None:
    '''
    Возвращает актуальную цену для материала.
    '''
    # Если сессия не передана, создаём свою
    if db_session is None:
        session = SessionLocal()
        close_session = True
    else:
        session = db_session
        close_session = False

    try:
        material = session.query(Material).filter(Material.name == material_name).first()
        if not material:
            logger.warning(f"Материал '{material_name}' не найден в БД")
            return None

        # Пробуем парсер
        if parser is not None:
            try:
                parsed = parser.fetch_price(material_name)

                source = session.query(PriceSource).filter(
                    PriceSource.name == parser.source_name
                ).first()

                if source:
                    price_entry = session.query(MaterialPrice).filter(
                        MaterialPrice.material_id == material.id,
                        MaterialPrice.source_id == source.id
                    ).first()

                    if price_entry:
                        price_entry.price_min = parsed.price_min
                        price_entry.price_avg = parsed.price_avg
                        price_entry.price_max = parsed.price_max
                        price_entry.updated_at = datetime.now(timezone.utc)
                    else:
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
                logger.warning(f"Парсер {parser.source_name} не смог получить цену для '{material_name}': {e}")

        # Fallback: seed-цена
        seed_source = session.query(PriceSource).filter(PriceSource.name == "seed").first()
        if not seed_source:
            logger.error("Источник 'seed' не найден в БД")
            return None

        seed_price = session.query(MaterialPrice).filter(
            MaterialPrice.material_id == material.id,
            MaterialPrice.source_id == seed_source.id
        ).first()

        if seed_price:
            logger.info(f"Цена для '{material_name}' взята из seed (fallback)")
        else:
            logger.warning(f"Seed-цена для '{material_name}' не найдена")

        return seed_price

    finally:
        if close_session:
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