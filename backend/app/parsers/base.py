from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal

# Заголовки/таймаут по умолчанию для requests-парсеров (были продублированы в
# labor_table_parser.py, rembrigada_parser.py, megastroy_parser.py — #278).
# Парсер может расширить/переопределить (см. megastroy_parser._build_headers).
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9",
}
DEFAULT_REQUEST_TIMEOUT = 10


@dataclass
class ParsedPrice:
    # Результат парсинга - три цены
    price_min: Decimal
    price_avg: Decimal
    price_max: Decimal
    # Ссылка на карточку/страницу, откуда взяты цены (для отображения источника
    # в смете). Необязательна: парсер может не знать ссылку → остаётся None.
    source_url: str | None = None


class BaseParser(ABC):
    '''
    Базовый класс для всех парсеров цен
    Каждый конкретный парсер (Мегастрой и т.д.) наследует этот класс
    и реализует метод fetch_price
    '''

    # Имя источника - должно совпадать с полем PriceSource.name в БД
    # Например: "Мегастрой"
    source_name: str

    def known_materials(self) -> list[str]:
        '''
        Список материалов, которые парсер умеет обрабатывать (используется
        CLI update_prices, чтобы знать, какие имена ему передавать). Пустой
        список по умолчанию — переопределяется парсерами материалов (см.
        MegastroyParser). Парсеры работ используют общий LABOR_SERVICE_MAP,
        а не этот метод.
        '''
        return []

    @abstractmethod
    def fetch_price(self, material_name: str) -> ParsedPrice:
        '''
        Получить цену по названию материала

        Если не удалось - просто кидаем исключение (Exception, ConnectionError и т.д.),
        агрегатор сам поймает и возьмет seed-цену

        material_name: название как в БД, например "Краска для стен"
        '''
        ...