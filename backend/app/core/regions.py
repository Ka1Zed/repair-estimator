'''
Единый список поддерживаемых городов (#394) — источник правды для валидации
EstimateRequest.city/ProjectCreate.city и для GET /api/regions.

Ограничен реально покрытыми регионами (см. covered_cities в
app/parsers/leman_parser.py и региональные seed-цены, docs/price-sources.md):
Казань — дефолт без своего регионального источника (базовые seed-цены,
region IS NULL), Москва/Санкт-Петербург — свои региональные источники.
Новый город добавляется здесь синхронно с docs/api.md и docs/price-sources.md.
'''

DEFAULT_REGION = "Казань"
SUPPORTED_CITIES = (DEFAULT_REGION, "Москва", "Санкт-Петербург")

_BY_CASEFOLD = {city.casefold(): city for city in SUPPORTED_CITIES}


def normalize_city(raw: str) -> str:
    '''
    Приводит введённый город к канонической форме из SUPPORTED_CITIES,
    сравнивая без учёта регистра и краевых пробелов («москва»/"Москва "/«МОСКВА»
    → «Москва»). Неизвестный город (опечатка, «Питер»/«СПб», незарегистрированный
    город) — ValueError с понятным сообщением; вызывающий pydantic-валидатор
    превращает его в 422, а не в тихий откат на дефолтный регион.
    '''
    canonical = _BY_CASEFOLD.get(raw.strip().casefold())
    if canonical is None:
        raise ValueError(
            f"Город '{raw}' не поддерживается. Доступные города: "
            f"{', '.join(SUPPORTED_CITIES)}."
        )
    return canonical
