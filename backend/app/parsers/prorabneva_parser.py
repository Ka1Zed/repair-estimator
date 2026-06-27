from app.parsers.labor_table_parser import LaborTableParser


class ProrabnevaParser(LaborTableParser):
    '''Прайс отделочных работ по Санкт-Петербургу (prorabneva.ru).'''

    source_name = "prorabneva.ru"
    region = "Санкт-Петербург"
    PRICE_URL = "https://www.prorabneva.ru/price"
