'''
Единый список источников цен: материалы и работы (базовые + региональные).

Единая точка добавления нового магазина/сайта — правка списков ниже, без
изменений в app/manage.py, app/api/estimates.py или price_aggregator_service.py.
Новый источник материалов (напр. Леман, #276) — новый класс парсера +
добавить его сюда; новый региональный сайт работ — то же самое.
'''
from app.parsers.base import BaseParser
from app.parsers.garantstroikompleks_parser import GarantStroiParser
from app.parsers.kaz_stroyka_parser import KazStroykaParser
from app.parsers.megastroy_parser import MegastroyParser
from app.parsers.otdelka_spb_parser import OtdelkaSpbParser
from app.parsers.prorabneva_parser import ProrabnevaParser
from app.parsers.rembrigada_parser import RembrigadaParser
from app.parsers.remont_uroven_parser import RemontUrovenParser

# Парсеры цен материалов. Сейчас один источник (Мегастрой); calc-код
# (estimates.get_material_parser) читает первый элемент — при добавлении
# второго источника логику выбора/комбинирования цен добавит сам #276.
MATERIAL_PARSERS: list[BaseParser] = [
    MegastroyParser(),
]

# Базовый (безрегиональный) прайс работ.
BASE_LABOR_PARSER: BaseParser = RembrigadaParser()

# Региональные прайсы работ. Rembrigada участвует дважды: как базовый прайс
# выше и как один из источников по Казани здесь.
REGIONAL_LABOR_PARSERS: list[BaseParser] = [
    GarantStroiParser(), RemontUrovenParser(),   # Москва
    OtdelkaSpbParser(), ProrabnevaParser(),       # Санкт-Петербург
    KazStroykaParser(), RembrigadaParser(),       # Казань
]
