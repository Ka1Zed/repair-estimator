from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal


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