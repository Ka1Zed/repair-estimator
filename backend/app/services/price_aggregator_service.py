import logging
import statistics
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Material, MaterialPrice, PriceSource, LaborService, LaborPrice
from app.parsers.base import BaseParser, ParsedPrice

logger = logging.getLogger(__name__)


def _normalize_price(price: Decimal, pack_size: Optional[Decimal]) -> Decimal:
    """
    Нормирует цену к единице измерения материала (л, кг, м², шт).
    Если pack_size задан (количество единиц в упаковке), цена делится на pack_size.
    Иначе цена считается уже за единицу.
    """
    if pack_size and pack_size > 0:
        return price / pack_size
    return price

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
    db: Session,
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

    db — сессия приходит от вызывающего (Depends(get_db) в эндпоинте, своя SessionLocal()
    в CLI) — эта функция сама сессию не открывает и не закрывает.
    '''
    if ttl_hours is None:
        ttl_hours = settings.PRICE_TTL_HOURS

    session = db
    material = session.query(Material).filter(Material.name == material_name).first()
    if not material:
        logger.warning(f"Материал '{material_name}' не найден в БД")
        return None

    # Пробуем парсер
    if parser is not None:
        source = session.query(PriceSource).filter(
            PriceSource.name == parser.source_name
        ).first()

        if source is None:
            # Источник парсера отсутствует в БД (например, добавили парсер в код,
            # но не досеяли price_sources — `python -m app.db.seed --missing`).
            # Без источника валидную цену некуда сохранить и нечего вернуть:
            # молча уходили бы в seed после успешного (и, для браузерных парсеров,
            # долгого) фетча. Логируем явно, чтобы это не выглядело как «парсер не
            # сработал».
            logger.warning(
                f"Источник '{parser.source_name}' не найден в price_sources — "
                f"цена парсера для '{material_name}' будет отброшена в seed. "
                "Досейте источник: python -m app.db.seed --missing"
            )

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

        # Живой сетевой запрос делаем только когда это явно разрешено: при
        # force_refresh (CLI update_prices) или PARSER_LIVE_FETCH=true (локалка).
        # На сервере (PARSER_LIVE_FETCH=false) в сеть не ходим: выше отдали бы
        # свежий кэш, иначе — seed-fallback ниже. Кэш на сервере наполняет
        # update_prices с российского IP.
        if force_refresh or settings.PARSER_LIVE_FETCH:
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
                        price_entry.source_url = parsed.source_url
                        price_entry.updated_at = datetime.now(timezone.utc)
                    else:
                        # Создаем новую
                        price_entry = MaterialPrice(
                            material_id=material.id,
                            source_id=source.id,
                            price_min=parsed.price_min,
                            price_avg=parsed.price_avg,
                            price_max=parsed.price_max,
                            source_url=parsed.source_url,
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


def _combine_labor_prices(session, service_id: int, rows: list[LaborPrice],
                          region: str | None) -> LaborPrice:
    '''
    Объединяет parser-цены нескольких сайтов одного региона в одну вилку:
    min = минимум по сайтам, max = максимум, avg = среднее средних (так среднее
    точнее, чем по одному прайсу). Возвращает несохраняемый (transient) LaborPrice.

    Представительный сайт — чья средняя ближе всего к объединённой средней: его
    показываем в строке сметы (source/source_url). Полный список сайтов кладём в
    транзитивный атрибут .contributing_sources (его читает estimates → поле sources).
    '''
    price_min = min(r.price_min for r in rows)
    price_max = max(r.price_max for r in rows)
    price_avg = Decimal(round(statistics.mean([r.price_avg for r in rows])))
    representative = min(rows, key=lambda r: abs(r.price_avg - price_avg))

    source_names = [
        s.name for s in session.query(PriceSource).filter(
            PriceSource.id.in_({r.source_id for r in rows})
        ).all()
    ]

    combined = LaborPrice(
        labor_service_id=service_id,
        source_id=representative.source_id,
        price_min=price_min,
        price_avg=price_avg,
        price_max=price_max,
        region=region,
        source_url=representative.source_url,
    )
    combined.contributing_sources = sorted(source_names)
    return combined


def get_labor_price(service_name: str, db: Session, region: str | None = None) -> LaborPrice | None:
    '''
    Возвращает цену работы. Источник правды — парсер (#144): сначала ищем валидные
    спарсенные цены (любой не-seed источник, записанный CLI update_prices), seed —
    только fallback.

    Сетевого запроса здесь нет: спарсенные цены работ пишет в БД команда
    `python -m app.manage update_prices`, а расчёт сметы их только читает.

    Свежесть parser-цены проверяется так же, как в кэше материалов (get_price):
    учитываются только цены моложе settings.PRICE_TTL_HOURS (по updated_at).
    Устаревшая parser-цена игнорируется — расчёт уходит на seed-fallback, чтобы
    в смете не висела цена, которую давно не обновляли (#167).

    Порядок выбора:
      1. parser-цены региона → 2. базовые parser-цены (region IS NULL),
      3. seed региона        → 4. базовая seed-цена (region IS NULL).
    Если на шаге 1/2 цену дали несколько сайтов — объединяем их вилки в одну
    (#166), иначе берём единственную. Строки parser-запроса сортируются по
    updated_at DESC: при нескольких источниках выбор детерминирован (самая свежая
    цена выигрывает тай-брейк представителя), что важно при региональных парсерах
    (#166). Нулевые/пустые и несвежие parser-цены игнорируются. Исключение наверх
    не пробрасываем.

    db — сессия приходит от вызывающего, эта функция сама её не открывает/закрывает.
    '''
    ttl_hours = settings.PRICE_TTL_HOURS
    session = db
    service = session.query(LaborService).filter(LaborService.name == service_name).first()
    if not service:
        logger.warning(f"Услуга '{service_name}' не найдена в БД")
        return None

    seed_source = session.query(PriceSource).filter(PriceSource.name == "seed").first()
    if not seed_source:
        logger.error("Источник 'seed' не найден в БД")
        return None

    def _usable(p: LaborPrice | None) -> bool:
        # Цену из парсера берём, только если она валидна (все > 0) И свежа
        # (моложе ttl_hours): устаревшую parser-цену игнорируем, как get_price.
        return (
            p is not None
            and all(v is not None and v > 0 for v in (p.price_min, p.price_avg, p.price_max))
            and _is_fresh(p.updated_at, ttl_hours)
        )

    # 1-2. Цены из парсеров (любой не-seed источник): сначала региональные,
    # при их отсутствии — базовые (region IS NULL). Несколько сайтов одного
    # уровня объединяем в одну вилку. Сортировка по updated_at DESC делает
    # выбор представителя детерминированным (самая свежая цена выигрывает).
    parser_q = session.query(LaborPrice).filter(
        LaborPrice.labor_service_id == service.id,
        LaborPrice.source_id != seed_source.id,
    ).order_by(LaborPrice.updated_at.desc())
    pool, scope_region = [], None
    if region is not None:
        region_rows = [p for p in parser_q.filter(LaborPrice.region == region).all() if _usable(p)]
        if region_rows:
            pool, scope_region = region_rows, region
    if not pool:
        base_rows = [p for p in parser_q.filter(LaborPrice.region.is_(None)).all() if _usable(p)]
        if base_rows:
            pool, scope_region = base_rows, None

    if pool:
        result = _combine_labor_prices(session, service.id, pool, scope_region)
        logger.info(
            f"Цена работы '{service_name}': источник=parser "
            f"({', '.join(result.contributing_sources)}), region={scope_region}"
        )
        return result

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


def update_labor_price(service_name: str, parser, db: Session, region: str | None = None) -> LaborPrice | None:
    '''
    Берет цену услуги через парсер и пишет в labor_prices с источником парсера.
    region — регион цены (город), пишется в LaborPrice.region; None для базовой
    (не региональной) цены. Запись адресуется по (услуга, источник, регион):
    у регионального парсера свой источник-сайт, поэтому регионы не конфликтуют.
    При любой ошибке парсера — ничего не меняет, возвращает None (старые цены остаются)

    db — сессия приходит от вызывающего (CLI update_prices сам открывает и закрывает
    SessionLocal() вокруг серии вызовов).
    '''
    session = db
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
        LaborPrice.source_id == source.id,
        LaborPrice.region == region,
    ).first()
    if not price:
        price = LaborPrice(labor_service_id=service.id, source_id=source.id, region=region)
        session.add(price)

    price.price_min = parsed.price_min
    price.price_avg = parsed.price_avg
    price.price_max = parsed.price_max
    price.source_url = parsed.source_url
    price.updated_at = datetime.now(timezone.utc)

    session.commit()
    session.refresh(price)
    logger.info(f"Цена услуги '{service_name}' обновлена от {parser.source_name}")
    return price