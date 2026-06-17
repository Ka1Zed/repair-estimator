from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal


@dataclass
class ParsedPrice:
    # Результат парсинга - три цены
    price_min: Decimal
    price_avg: Decimal
    price_max: Decimal


class BaseParser(ABC):
    '''
    Базовый класс для всех парсеров цен
    Каждый конкретный парсер (Мегастрой, Avito и т.д.) наследует этот класс
    и реализует метод fetch_price
    '''

    # Имя источника - должно совпадать с полем PriceSource.name в БД
    # Например: "Мегастрой", "Avito"
    source_name: str

    @abstractmethod
    def fetch_price(self, material_name: str) -> ParsedPrice:
        '''
        Получить цену по названию материала

        Если не удалось - просто кидаем исключение (Exception, ConnectionError и т.д.),
        агрегатор сам поймает и возьмет seed-цену

        material_name: название как в БД, например "Краска для стен"
        '''
        ...