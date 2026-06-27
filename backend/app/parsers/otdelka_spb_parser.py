from app.parsers.labor_table_parser import LaborTableParser


class OtdelkaSpbParser(LaborTableParser):
    '''Прайс отделочных работ по Санкт-Петербургу (otdelka-spb.ru).'''

    source_name = "otdelka-spb.ru"
    region = "Санкт-Петербург"
    PRICE_URL = "https://otdelka-spb.ru/prajjs/"
