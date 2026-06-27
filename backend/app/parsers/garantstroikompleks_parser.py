from app.parsers.labor_table_parser import LaborTableParser


class GarantStroiParser(LaborTableParser):
    '''Прайс отделочных работ по Москве (garantstroikompleks.ru).'''

    source_name = "garantstroikompleks.ru"
    region = "Москва"
    PRICE_URL = "https://garantstroikompleks.ru/prajs-list"
