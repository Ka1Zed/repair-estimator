import sys
import logging

from app.parsers.megastroy_parser import MegastroyParser, CATEGORY_MAP
from app.services.price_aggregator_service import get_price, update_labor_price

from app.parsers.rembrigada_parser import RembrigadaParser, SERVICE_MAP
from app.parsers.labor_table_parser import LABOR_SERVICE_MAP
from app.parsers.garantstroikompleks_parser import GarantStroiParser
from app.parsers.remont_uroven_parser import RemontUrovenParser
from app.parsers.otdelka_spb_parser import OtdelkaSpbParser
from app.parsers.prorabneva_parser import ProrabnevaParser
from app.parsers.kaz_stroyka_parser import KazStroykaParser

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
    parser = MegastroyParser()

    # Берем список материалов, которые умеет парсить Мегастрой
    material_names = list(CATEGORY_MAP.keys())

    logger.info(f"Старт обновления цен. Материалов к обработке: {len(material_names)}")

    success = 0
    failed = 0

    for name in material_names:
        try:
            price = get_price(name, parser=parser, force_refresh=True)
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

    # услуги по прайсам ремонтных компаний

    labor_parser = RembrigadaParser()
    logger.info(f"Обновление цен услуг: {len(SERVICE_MAP)} позиций")
    for service in SERVICE_MAP:
        try:
            price = update_labor_price(service, parser=labor_parser)
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
    regional_labor_parsers = [
        GarantStroiParser(), RemontUrovenParser(),   # Москва
        OtdelkaSpbParser(), ProrabnevaParser(),       # Санкт-Петербург
        KazStroykaParser(), RembrigadaParser(),       # Казань
    ]
    for labor_parser in regional_labor_parsers:
        logger.info(
            f"Региональный прайс работ: {labor_parser.source_name} "
            f"({labor_parser.region}), {len(LABOR_SERVICE_MAP)} позиций"
        )
        for service in LABOR_SERVICE_MAP:
            try:
                price = update_labor_price(
                    service, parser=labor_parser, region=labor_parser.region
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