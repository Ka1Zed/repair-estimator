import logging
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.db.session import SessionLocal
from app.db.models import Material, MaterialPrice, PriceSource, LaborService, LaborPrice
from app.parsers.base import BaseParser, ParsedPrice

logger = logging.getLogger(__name__)


def _is_fresh(updated_at: datetime | None, ttl_hours: int) -> bool:
    '''Цена считается актуальной, если её обновляли позже, чем ttl_hours назад.'''
    if updated_at is None:
        return False
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - updated_at < timedelta(hours=ttl_hours)


def _is_valid_parsed(parsed: ParsedPrice | None) -> bool:
    '''
    Результат парсера валиден, только если все три цены заданы и строго положительны.

    При VPN/блок-странице сайт может вернуть HTTP 200 с мусором → парсер не падает,
    а отдаёт нулевую/пустую цену. Такой ответ НЕ считаем ценой: его нельзя ни возвращать
    наверх (иначе в смете 0), ни сохранять в БД (иначе кэш закрепит 0 на весь TTL).
    Вместо этого вызывающий код откатывается на seed — наравне с веткой except.
    '''
    if parsed is None:
        return False
    for value in (parsed.price_min, parsed.price_avg, parsed.price_max):
        if value is None or value <= 0:
            return False
    return True


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
                logger.info(f"Цена для '{material_name}': источник=cache ({parser.source_name})")
                return price_entry

            try:
                parsed = parser.fetch_price(material_name)

                # Нулевую/пустую цену (VPN/блок-страница) не сохраняем и не возвращаем —
                # это закрепило бы 0 в кэше на весь TTL. Уходим в seed, как при исключении.
                if not _is_valid_parsed(parsed):
                    logger.warning(
                        f"Парсер {parser.source_name} вернул пустую/нулевую цену для "
                        f"'{material_name}' — fallback на seed (parser=0/empty)"
                    )
                elif source:
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
                    logger.info(f"Цена для '{material_name}': источник=parser ({parser.source_name})")
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
            logger.info(f"Цена для '{material_name}': источник=seed (fallback), region={region}")
        else:
            logger.warning(f"Seed-цена для '{material_name}' не найдена")

        return seed_price

    finally:
        session.close()


def get_labor_price(service_name: str, region: str | None = None) -> LaborPrice | None:
    '''
    Возвращает цену работы. Источник правды — парсер (#144): сначала ищем валидную
    спарсенную цену (любой не-seed источник, записанный CLI update_prices), seed —
    только fallback.

    Сетевого запроса здесь нет: спарсенные цены работ пишет в БД команда
    `python -m app.manage update_prices`, а расчёт сметы их только читает — тот же
    TTL-замысел, что и у кэша материалов.

    Порядок выбора:
      1. parser-цена региона → 2. базовая parser-цена (region IS NULL),
      3. seed региона        → 4. базовая seed-цена (region IS NULL).
    Нулевые/пустые parser-цены игнорируются (как и в get_price). Исключение наверх
    не пробрасываем.
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

        def _valid(p: LaborPrice | None) -> bool:
            return p is not None and all(
                v is not None and v > 0 for v in (p.price_min, p.price_avg, p.price_max)
            )

        # 1-2. Цена из парсера (любой не-seed источник): региональная, затем базовая.
        parser_q = session.query(LaborPrice).filter(
            LaborPrice.labor_service_id == service.id,
            LaborPrice.source_id != seed_source.id,
        )
        parser_price = None
        if region is not None:
            parser_price = parser_q.filter(LaborPrice.region == region).first()
        if not _valid(parser_price):
            parser_price = parser_q.filter(LaborPrice.region.is_(None)).first()
        if _valid(parser_price):
            logger.info(f"Цена работы '{service_name}': источник=parser, region={region}")
            return parser_price

        # 3-4. Fallback на seed: региональная, затем базовая.
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
            logger.info(f"Цена работы '{service_name}': источник=seed (fallback), region={region}")
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

        # Нулевую/пустую цену не сохраняем — старые цены остаются, расчёт уйдёт на seed.
        if not _is_valid_parsed(parsed):
            logger.warning(
                f"Парсер {parser.source_name} вернул пустую/нулевую цену для "
                f"'{service_name}' — не сохраняем (parser=0/empty)"
            )
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