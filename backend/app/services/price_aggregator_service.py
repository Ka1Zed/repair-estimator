import logging
import statistics
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import MaterialPrice, PriceSource, LaborService, LaborPrice
from app.parsers.base import BaseParser, ParsedPrice
from app.services._query_cache import (
    labor_service_by_name, material_by_name, source_by_name, source_name_by_id,
)
from app.services.repair_coeffs_service import clamp_price_corridor

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
    3. Если рефетч не удался (или PARSER_LIVE_FETCH=false), но старая цена этого
       парсера младше PRICE_STALE_TTL_HOURS — возвращаем её как есть: реальная
       цена недельной давности точнее общего seed.
    4. Если парсер упал/не передан/нет источника/цена старше PRICE_STALE_TTL_HOURS —
       берём seed-цену из БД. При заданном region сначала ищем seed-цену этого
       региона, при отсутствии — базовую seed-цену с region IS NULL.
    5. force_refresh=True заставляет дёрнуть парсер даже при свежем кэше (для CLI update_prices).
    6. Наверх исключение не пробрасываем никогда.

    Аргумент region используется ТОЛЬКО в seed-fallback (п.3). Ветка парсера (п.1-2)
    региону-аргументу не подчиняется — она адресует кэш по region САМОГО инстанса
    парсера (`parser.region`, #345, напр. LEMAN_MOSCOW), а не по тому, что запросил
    вызывающий. Большинство парсеров (Мегастрой, базовый Леман) region не задают
    (None) — их цены, как и раньше, region IS NULL независимо от запрошенного города.

    db — сессия приходит от вызывающего (Depends(get_db) в эндпоинте, своя SessionLocal()
    в CLI) — эта функция сама сессию не открывает и не закрывает.
    '''
    if ttl_hours is None:
        ttl_hours = settings.PRICE_TTL_HOURS

    session = db
    material = material_by_name(session, material_name)
    if not material:
        logger.warning(f"Материал '{material_name}' не найден в БД")
        return None

    # Пробуем парсер
    if parser is not None:
        source = source_by_name(session, parser.source_name)

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

        # Регион ЭТОГО инстанса парсера (#345, напр. LEMAN_MOSCOW.region ==
        # "Москва") — НЕ аргумент region функции (тот только для seed ниже).
        # Кэш адресуется (материал, источник, регион парсера), чтобы разные
        # региональные инстансы одного источника (Леман Казань/Москва/СПб —
        # общий source_id "Леман") не перезаписывали цены друг друга.
        parser_region = parser.region
        price_entry = None
        if source:
            price_query = session.query(MaterialPrice).filter(
                MaterialPrice.material_id == material.id,
                MaterialPrice.source_id == source.id,
            )
            if parser_region is not None:
                price_query = price_query.filter(MaterialPrice.region == parser_region)
            else:
                price_query = price_query.filter(MaterialPrice.region.is_(None))
            price_entry = price_query.first()

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
                # reference_package_size (#382) — справочная фасовка материала,
                # участвует в выборе товара-представителя (#395, select_representative)
                # для любых материалов. Отсев нетиповой мелкой фасовки ДО статистики
                # (filter_undersized_packages) включаем только для кг-материалов —
                # именно на них проверено допущение «типовая закупка — мешками»
                # (#382). У краски-премиум оно не подтвердилось: декоративная банка
                # 0.9-1 л — легитимный формат, а не выброс, фильтр ложно её отсекал
                # (#389). См. docs/price-sources.md.
                reference_package_size = (
                    Decimal(str(material.package_size)) if material.package_size else None
                )
                apply_undersized_filter = material.unit == "кг"
                parsed = parser.fetch_price(
                    material_name,
                    reference_package_size=reference_package_size,
                    apply_undersized_filter=apply_undersized_filter,
                )

                # Нулевую/пустую цену (VPN/блок-страница) не сохраняем и не возвращаем —
                # это закрепило бы 0 в кэше на весь TTL. Уходим в seed, как при исключении.
                if not _is_valid_parsed(parsed):
                    logger.warning(
                        f"Парсер {parser.source_name} вернул пустую/нулевую цену для "
                        f"'{material_name}' — fallback на seed (parser=0/empty)"
                    )
                elif source:
                    # package_size (#306) — фасовка конкретного товара за
                    # source_url, а не справочная Material.package_size.
                    package_size = (
                        float(parsed.package_size) if parsed.package_size is not None else None
                    )
                    if price_entry:
                        # Обновляем
                        price_entry.price_min = parsed.price_min
                        price_entry.price_avg = parsed.price_avg
                        price_entry.price_max = parsed.price_max
                        price_entry.source_url = parsed.source_url
                        price_entry.package_size = package_size
                        price_entry.updated_at = datetime.now(timezone.utc)
                    else:
                        # Создаем новую
                        price_entry = MaterialPrice(
                            material_id=material.id,
                            source_id=source.id,
                            region=parser_region,
                            price_min=parsed.price_min,
                            price_avg=parsed.price_avg,
                            price_max=parsed.price_max,
                            source_url=parsed.source_url,
                            package_size=package_size,
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

        # Живой рефетч не удался (или выключен), но старая цена ЭТОГО парсера
        # ещё не совсем протухла (< PRICE_STALE_TTL_HOURS) — она точнее общего
        # seed, отдаём её вместо seed-fallback ниже.
        if price_entry and _is_fresh(price_entry.updated_at, settings.PRICE_STALE_TTL_HOURS):
            logger.warning(
                f"Цена для '{material_name}': источник=parser устаревшая "
                f"({parser.source_name}, updated_at={price_entry.updated_at}) — "
                "живой рефетч не удался, но кэш ещё не старше PRICE_STALE_TTL_HOURS"
            )
            return price_entry

    # Fallback: берем seed-цену из БД
    seed_source = source_by_name(session, "seed")
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


def _combined_avg(rows) -> Decimal:
    '''
    Средняя объединённой вилки нескольких источников (#412).

    Источник с реальным распределением цен (min<max: терции эконом→стандарт→премиум)
    представляет тело рынка. Одиночный ПЛОСКИЙ прайс (min==max, напр. премиальный
    подрядчик с единственной строкой) — лишь точка, и при «среднем средних» такой
    выброс тянет avg наравне с целым распределением (живая сверка #407: kaz-стройка
    даёт 600..3000, а плоский подрядчик — 3300, объединение давало avg≈2466 против
    тела ~1000..1600). Поэтому центр считаем ТОЛЬКО по неплоским источникам, если они
    есть: плоские по-прежнему участвуют в выборе границ вилки (min_row/max_row), но
    не тянут центр. Если все источники плоские — обычное среднее (усреднять больше
    нечего). Границы вилки эта функция не трогает — только avg.
    '''
    spread = [r for r in rows if r.price_max > r.price_min]
    basis = spread or rows
    return Decimal(round(statistics.mean([r.price_avg for r in basis])))


def _combine_material_prices(session, material_id: int,
                              rows: list[MaterialPrice]) -> MaterialPrice:
    '''
    Объединяет parser-цены нескольких источников материала (Мегастрой, Леман, ...)
    в одну вилку — аналог _combine_labor_prices (#166), но для материалов и с учётом
    package_size (#306): у представителя берём и source_url, и его package_size,
    т.к. это фасовка КОНКРЕТНОГО товара за этой ссылкой (расчёт упаковок должен
    остаться согласован с тем, что видно по ссылке).

    region берём у представителя, а не из запроса: у большинства источников
    (Мегастрой, базовый Леман) region IS NULL, как и раньше (одна цена на все
    города), но у региональных источников (#345, напр. LEMAN_MOSCOW) — реальный
    город этого источника, а не эхо запрошенного (см. get_price про region
    самого парсера vs аргумент region).

    Работает и для одного элемента rows (тогда вилка/представитель — этот же элемент),
    чтобы contributing_sources был заполнен и для единственного источника (как у labor).

    Band КАЖДОГО источника прижимается к коридору по ЕГО средней ДО выбора границ
    (#411, clamp_price_corridor): категорийный price-band одного источника (нижняя/
    верхняя треть цен категории) гасится, а настоящая межисточниковая дисперсия
    (min по одному источнику vs max по другому) проходит в вилку без клампа.

    min_row/max_row (#348) — строки, чьи клампнутые price_min/price_max реально стали
    границами вилки. Ссылку на границу не кладём (null), если эта строка совпадает с
    представителем (дублировать source_url нечего) ИЛИ если границу задал кламп, а не
    сырая цена источника (показанная цена уже не равна цене этого источника).
    '''
    clamped = {id(r): clamp_price_corridor(r.price_min, r.price_avg, r.price_max) for r in rows}
    min_row = min(rows, key=lambda r: clamped[id(r)][0])
    max_row = max(rows, key=lambda r: clamped[id(r)][1])
    price_min = clamped[id(min_row)][0]
    price_max = clamped[id(max_row)][1]
    price_avg = _combined_avg(rows)
    representative = min(rows, key=lambda r: abs(r.price_avg - price_avg))

    source_names = [
        name for name in (
            source_name_by_id(session, sid) for sid in {r.source_id for r in rows}
        ) if name is not None
    ]

    min_is_clamp = price_min != min_row.price_min
    max_is_clamp = price_max != max_row.price_max
    min_attributable = min_row.source_id != representative.source_id and not min_is_clamp
    max_attributable = max_row.source_id != representative.source_id and not max_is_clamp

    combined = MaterialPrice(
        material_id=material_id,
        source_id=representative.source_id,
        price_min=price_min,
        price_avg=price_avg,
        price_max=price_max,
        region=representative.region,
        source_url=representative.source_url,
        package_size=representative.package_size,
        updated_at=representative.updated_at,
    )
    combined.contributing_sources = sorted(source_names)
    combined.min_source_id = min_row.source_id if min_attributable else None
    combined.min_source_url = min_row.source_url if min_attributable else None
    combined.max_source_id = max_row.source_id if max_attributable else None
    combined.max_source_url = max_row.source_url if max_attributable else None
    return combined


def _select_regional_parsers(parsers: list[BaseParser], city: str | None) -> list[BaseParser]:
    '''
    Некоторые источники материалов покрывают только конкретные города (#345,
    напр. LEMAN_MOSCOW/LEMAN_SPB — свой домен и facet наличия по магазинам этого
    города, см. leman_parser.py). Если среди parsers есть источник(и), чей
    covered_cities включает запрошенный city, — берём ТОЛЬКО их: иначе цена
    источника без городской привязки (напр. Мегастрой, который физически не
    работает в Москве/СПб) утекла бы в вилку города, которого не покрывает.

    Если ни один источник не покрывает именно этот город — берём все источники
    без covered_cities (текущее поведение по умолчанию, единственный регион —
    Казань). Источник со своим covered_cities, не совпадающим с city, никогда
    не попадает в эту "по умолчанию" группу — иначе цена одного города могла бы
    подмешаться в смету другого.
    '''
    exact = [p for p in parsers if city is not None and p.covered_cities and city in p.covered_cities]
    if exact:
        return exact
    return [p for p in parsers if not p.covered_cities]


def get_available_stores(parsers: list[BaseParser], city: str | None) -> list[dict]:
    '''
    Справочник магазинов материалов с признаком доступности для города (#363) —
    для явного выбора магазина пользователем (см. store_names в get_material_price),
    вместо скрытого автоподбора по covered_cities.

    Использует ту же _select_regional_parsers, что и get_material_price: магазин
    (уникальный source_name среди parsers) доступен, если хотя бы один его инстанс
    попадает в выборку для этого города. Так гарантируется согласованность со
    списком источников, который реально участвует в расчёте.
    '''
    selected_names = {p.source_name for p in _select_regional_parsers(parsers, city)}
    all_names = sorted({p.source_name for p in parsers})
    return [{"name": name, "available": name in selected_names} for name in all_names]


def get_material_price(
    material_name: str,
    db: Session,
    parsers: list[BaseParser],
    region: str | None = None,
    ttl_hours: int | None = None,
    store_names: list[str] | None = None,
) -> MaterialPrice | None:
    '''
    Возвращает цену материала, объединённую по всем зарегистрированным источникам
    (#333) — по аналогии с get_labor_price/_combine_labor_prices.

    region здесь — это и запрошенный город (для выбора источников через
    _select_regional_parsers, #345), и seed-fallback регион, пробрасываемый в
    get_price как раньше.

    store_names (#363) — явный выбор пользователя (напр. только "Леман"): сужает
    уже отобранные для города источники до перечисленных по source_name. Если
    после сужения источников не осталось (выбранный магазин не покрывает этот
    город) — откатываемся на полный набор для города, как будто store_names не
    задан: расчёт не должен падать или оставаться без цены из-за недоступного
    в городе магазина.

    Для каждого выбранного парсера вызывает get_price (там уже реализованы
    кэш/TTL, живой fetch при PARSER_LIVE_FETCH и seed-fallback для ОДНОГО
    источника) и разбирает результаты: parser-цены (не seed) объединяются в
    одну вилку через _combine_material_prices; если валидных parser-цен нет ни
    у одного источника — возвращаем seed-результат (у всех парсеров он
    одинаковый, достаточно любого).

    Источников 0 (пустой parsers) — вернётся seed, как раньше при одном парсере.
    '''
    seed_source = source_by_name(db, "seed")

    material = material_by_name(db, material_name)
    if not material:
        logger.warning(f"Материал '{material_name}' не найден в БД")
        return None

    selected_parsers = _select_regional_parsers(parsers, region)
    if store_names:
        narrowed = [p for p in selected_parsers if p.source_name in store_names]
        if narrowed:
            selected_parsers = narrowed

    parser_results: list[MaterialPrice] = []
    seed_result: MaterialPrice | None = None
    for parser in selected_parsers:
        result = get_price(material_name, db=db, parser=parser, region=region, ttl_hours=ttl_hours)
        if result is None:
            continue
        if seed_source is not None and result.source_id == seed_source.id:
            seed_result = result
        else:
            parser_results.append(result)

    if parser_results:
        combined = _combine_material_prices(db, material.id, parser_results)
        logger.info(
            f"Цена материала '{material_name}': источник=parser "
            f"({', '.join(combined.contributing_sources)}), region={region}"
        )
        return combined

    if seed_result is None:
        return None
    # Seed минует _combine (единственный источник), но его band — тот же категорийный
    # price-band, что и у парсеров, и его тоже надо прижать к коридору (#411).
    # Возвращаем транзитный клон (не мутируем персистентную seed-строку — иначе
    # автофлаш сессии затёр бы seed в БД) без contributing_sources (контракт seed).
    c_min, c_max = clamp_price_corridor(
        seed_result.price_min, seed_result.price_avg, seed_result.price_max
    )
    return MaterialPrice(
        material_id=seed_result.material_id,
        source_id=seed_result.source_id,
        price_min=c_min,
        price_avg=seed_result.price_avg,
        price_max=c_max,
        region=seed_result.region,
        source_url=seed_result.source_url,
        package_size=seed_result.package_size,
        updated_at=seed_result.updated_at,
    )


def _combine_labor_prices(session, service_id: int, rows: list[LaborPrice],
                          region: str | None, *, clamp: bool = True) -> LaborPrice:
    '''
    Объединяет parser-цены нескольких сайтов одного региона в одну вилку:
    min = минимум по сайтам, max = максимум, avg = средняя по неплоским сайтам
    (см. _combined_avg, #412: одиночный плоский прайс не тянет центр). Возвращает
    несохраняемый (transient) LaborPrice.

    Представительный сайт — чья средняя ближе всего к объединённой средней: его
    показываем в строке сметы (source/source_url). Полный список сайтов кладём в
    транзитивный атрибут .contributing_sources (его читает estimates → поле sources).

    Band каждого сайта прижимается к коридору по его средней ДО выбора границ (#411,
    clamp_price_corridor) — как у материалов: внутрисайтовый категорийный разброс
    гасится, реальная межсайтовая (межподрядная) дисперсия проходит без клампа. Для
    работ это особенно важно: у них нет tier-вариантов SKU, и межисточниковый разброс —
    единственный канал реального рыночного разброса. clamp=False отключает кламп —
    справочный блок скрытых работ намеренно показывает широкую вилку риска (#239).

    min_row/max_row (#348) — сайты, чьи клампнутые price_min/price_max реально стали
    границами вилки. Ссылку на границу не кладём (null), если сайт совпадает с
    представителем ИЛИ границу задал кламп, а не сырая цена сайта.
    '''
    def _band(r: LaborPrice) -> tuple[Decimal, Decimal]:
        if clamp:
            return clamp_price_corridor(r.price_min, r.price_avg, r.price_max)
        return (r.price_min, r.price_max)
    clamped = {id(r): _band(r) for r in rows}
    min_row = min(rows, key=lambda r: clamped[id(r)][0])
    max_row = max(rows, key=lambda r: clamped[id(r)][1])
    price_min = clamped[id(min_row)][0]
    price_max = clamped[id(max_row)][1]
    price_avg = _combined_avg(rows)
    representative = min(rows, key=lambda r: abs(r.price_avg - price_avg))

    source_names = [
        name for name in (
            source_name_by_id(session, sid) for sid in {r.source_id for r in rows}
        ) if name is not None
    ]

    min_is_clamp = price_min != min_row.price_min
    max_is_clamp = price_max != max_row.price_max
    min_attributable = min_row.source_id != representative.source_id and not min_is_clamp
    max_attributable = max_row.source_id != representative.source_id and not max_is_clamp

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
    combined.min_source_id = min_row.source_id if min_attributable else None
    combined.min_source_url = min_row.source_url if min_attributable else None
    combined.max_source_id = max_row.source_id if max_attributable else None
    combined.max_source_url = max_row.source_url if max_attributable else None
    return combined


def get_labor_price(service_name: str, db: Session, region: str | None = None,
                    clamp: bool = True) -> LaborPrice | None:
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

    clamp=True (по умолчанию) прижимает band каждого источника к коридору per-source
    (#411) — так берёт цену основная смета. clamp=False отдаёт сырой band: его
    запрашивает справочный блок скрытых работ (#239), где широкая вилка риска —
    осознанный сигнал, а не категорийный шум, и кламп её бы схлопнул.
    '''
    ttl_hours = settings.PRICE_TTL_HOURS
    session = db
    service = labor_service_by_name(session, service_name)
    if not service:
        logger.warning(f"Услуга '{service_name}' не найдена в БД")
        return None

    seed_source = source_by_name(session, "seed")
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
        result = _combine_labor_prices(session, service.id, pool, scope_region, clamp=clamp)
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

    if price is None:
        logger.warning(f"Seed-цена для работы '{service_name}' не найдена")
        return None

    logger.info(f"Цена работы '{service_name}': источник=seed (fallback), region={region}")
    if not clamp:
        # Справочный блок скрытых работ (#239) берёт сырой seed-band — кламп бы
        # схлопнул намеренно широкую вилку риска. Персистентную строку не мутируем.
        return price
    # Как у материалов (#411): seed минует _combine, но его band тоже категорийный —
    # клампим к коридору. Транзитный клон, чтобы не затереть seed в БД автофлашем.
    c_min, c_max = clamp_price_corridor(price.price_min, price.price_avg, price.price_max)
    return LaborPrice(
        labor_service_id=price.labor_service_id,
        source_id=price.source_id,
        price_min=c_min,
        price_avg=price.price_avg,
        price_max=c_max,
        region=price.region,
        source_url=price.source_url,
        updated_at=price.updated_at,
    )


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

    try:
        session.commit()
    except Exception:
        # Без rollback транзакция остаётся aborted, и все последующие запросы по
        # общей сессии падают с InFailedSqlTransaction. Откатываем и пробрасываем
        # настоящую ошибку вызывающему (он залогирует и пойдёт дальше по чистой сессии).
        session.rollback()
        raise
    session.refresh(price)
    logger.info(f"Цена услуги '{service_name}' обновлена от {parser.source_name}")
    return price