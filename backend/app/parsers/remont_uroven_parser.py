from app.parsers.labor_table_parser import LaborTableParser


class RemontUrovenParser(LaborTableParser):
    '''Прайс отделочных работ по Москве (remont-uroven.ru).'''

    source_name = "remont-uroven.ru"
    region = "Москва"
    PRICE_URL = "https://remont-uroven.ru/price.html"
