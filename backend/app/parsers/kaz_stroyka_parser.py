import re

from app.parsers.labor_table_parser import LaborTableParser


class KazStroykaParser(LaborTableParser):
    '''
    Прайс отделочных работ по Казани (kaz-stroyka.ru).

    Отделка, электрика и сантехника опубликованы отдельными страницами —
    парсим все три. В ячейку названия попадает раскрытый текст «подробнее
    что входит в состав работ» и пояснения в скобках («затирка швов
    считается отдельно» и т.п.) — обрезаем название по слову «подробнее»
    и по первой скобке, иначе include/exclude слова LABOR_SERVICE_MAP
    матчатся по описанию, а не по названию работы.
    '''

    source_name = "kaz-stroyka.ru"
    region = "Казань"
    # Страница отделки весит ~4 МБ (раскрытые описания работ) — дефолтных
    # 10 секунд на медленном соединении может не хватить.
    request_timeout = 30
    PRICE_URL = "https://www.kaz-stroyka.ru/prajs-otdelka.html"
    EXTRA_PAGE_URLS = (
        "https://www.kaz-stroyka.ru/prajs-elektrika.html",
        "https://www.kaz-stroyka.ru/prajs-santekhnika.html",
    )

    def _page_urls(self) -> list[str]:
        return [self.PRICE_URL, *self.EXTRA_PAGE_URLS]

    def _clean_name(self, name: str) -> str:
        return re.split(r"\(|подробнее", name)[0].strip()
