import sys
import logging
from contextlib import nullcontext

from app.db.session import SessionLocal
from app.parsers.labor_table_parser import LABOR_SERVICE_MAP
from app.parsers.registry import BASE_LABOR_PARSER, MATERIAL_PARSERS, REGIONAL_LABOR_PARSERS
from app.services.price_aggregator_service import get_price, update_labor_price

# Настройка логирования — чтобы видеть прогресс в консоли
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def update_prices():
    '''
    Обновляет цены через доступные парсеры.
    Каждый материал обрабатывается отдельно: ошибка одного
    не прерывает обработку остальных.
    '''
    success = 0
    failed = 0

    # CLI не в FastAPI-запросе — сессию открываем и закрываем сами вокруг всей
    # серии вызовов (Depends здесь недоступен).
    db = SessionLocal()
    try:
        # Материалы: каждый зарегистрированный парсер обрабатывает свой список
        # (parser.known_materials()) — добавление нового источника (напр. Леман,
        # #276) не требует правок этой функции, только app/parsers/registry.py.
        for parser in MATERIAL_PARSERS:
            material_names = parser.known_materials()
            logger.info(
                f"Обновление цен материалов ({parser.source_name}): "
                f"{len(material_names)} позиций"
            )
            # Браузерные парсеры (Леман) умеют отдать общую сессию — один Chrome
            # на все материалы вместо нового процесса на каждую категорию (#277).
            # Парсеры без такого метода (Мегастрой, requests-based) не затронуты.
            open_session = getattr(parser, "open_session", None)
            session_cm = open_session() if open_session else nullcontext(None)
            with session_cm as session:
                if session is not None and hasattr(parser, "set_session"):
                    parser.set_session(session)
                try:
                    for name in material_names:
                        try:
                            price = get_price(name, db=db, parser=parser, force_refresh=True)
                            if price:
                                logger.info(f"  ✓ {name}: avg={price.price_avg}")
                                success += 1
                            else:
                                logger.warning(f"  ✗ {name}: цена не найдена (нет в БД)")
                                failed += 1
                        except Exception as e:
                            # агрегатор и так глотает ошибки парсера, но на всякий случай
                            logger.error(f"  ✗ {name}: непредвиденная ошибка — {e}")
                            failed += 1
                finally:
                    if hasattr(parser, "set_session"):
                        parser.set_session(None)

        # услуги по прайсам ремонтных компаний

        logger.info(f"Обновление цен услуг: {len(LABOR_SERVICE_MAP)} позиций")
        for service in LABOR_SERVICE_MAP:
            try:
                price = update_labor_price(service, parser=BASE_LABOR_PARSER, db=db)
                if price:
                    logger.info(f"  ✓ {service}: avg={price.price_avg}")
                    success += 1
                else:
                    logger.warning(f"  ✗ {service}: не обновлено (fallback на seed)")
                    failed += 1
            except Exception as e:
                logger.error(f"  ✗ {service}: {e}")
                failed += 1

        # Региональные прайсы отделочных работ: цены пишутся с region сайта.
        # Ошибка одного сайта/услуги не прерывает остальные.
        for labor_parser in REGIONAL_LABOR_PARSERS:
            logger.info(
                f"Региональный прайс работ: {labor_parser.source_name} "
                f"({labor_parser.region}), {len(LABOR_SERVICE_MAP)} позиций"
            )
            for service in LABOR_SERVICE_MAP:
                try:
                    price = update_labor_price(
                        service, parser=labor_parser, region=labor_parser.region, db=db
                    )
                    if price:
                        logger.info(f"  ✓ {service} [{labor_parser.region}]: avg={price.price_avg}")
                        success += 1
                    else:
                        logger.warning(
                            f"  ✗ {service} [{labor_parser.region}]: не обновлено (fallback на seed)"
                        )
                        failed += 1
                except Exception as e:
                    logger.error(f"  ✗ {service} [{labor_parser.region}]: {e}")
                    failed += 1
    finally:
        db.close()

    logger.info(f"Готово. Успешно: {success}, с проблемами: {failed}")


# Простой роутинг команд
COMMANDS = {
    "update_prices": update_prices,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print("Использование: python -m app.manage <команда>")
        print(f"Доступные команды: {', '.join(COMMANDS.keys())}")
        sys.exit(1)

    COMMANDS[sys.argv[1]]()


if __name__ == "__main__":
    main()