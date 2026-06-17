import logging
from datetime import datetime, timezone
# from decimal import Decimal

from app.db.session import SessionLocal
from app.db.models import Material, MaterialPrice, PriceSource
from app.parsers.base import BaseParser

logger = logging.getLogger(__name__)


def get_price(material_name: str, parser: BaseParser | None = None) -> MaterialPrice | None:
    '''
    Возвращает актуальную цену для материала

    Логика:
    1. Если парсер передан - пробуем получить цену через него
    2. Если парсер упал (любая ошибка) или не передан - берём seed-цену из БД.
    3. При успешном парсинге - сохраняем свежую цену в БД (source = парсер)
    4. Наверх исключение не пробрасываем никогда
    '''
    session = SessionLocal()
    try:
        material = session.query(Material).filter(Material.name == material_name).first()
        if not material:
            logger.warning(f"Материал '{material_name}' не найден в БД")
            return None

        # Пробуем парсер
        if parser is not None:
            try:
                parsed = parser.fetch_price(material_name)

                # Находим или создаем запись источника
                source = session.query(PriceSource).filter(
                    PriceSource.name == parser.source_name
                ).first()

                if source:
                    # Ищем существующую запись цены для этого источника
                    price_entry = session.query(MaterialPrice).filter(
                        MaterialPrice.material_id == material.id,
                        MaterialPrice.source_id == source.id
                    ).first()

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
        session.close()