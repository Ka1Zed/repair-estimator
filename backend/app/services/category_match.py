"""Определение товара из смежной категории по slug'у source_url (#406).

Бэкенд отдаёт резолвленный товар под ИМЕНЕМ материала (avg_item.name = «Краска
потолочная»), а реальный тайтл карточки («краска для древесины») виден только в
slug'е source_url. Надёжного структурного признака категории у нас нет, поэтому
сверяем slug со списком запрещённых токенов смежных категорий, заданным на
материале (Material.category_exclusions).

Детект работает и на проде: считается из УЖЕ сохранённого source_url на этапе
/calculate, а не в момент живого фетча (на сервере PARSER_LIVE_FETCH=false, цены
приходят из кэша, наполненного update_prices).

Только запрет (без positive-require): честно широкие категории (плитка 359→4637 ₽)
не должны давать ложных срабатываний — товар помечаем, только если в slug'е реально
всплыл токен чужой категории.
"""


def detect_category_mismatch(
    source_url: str | None, exclusions: list[str] | None
) -> bool:
    """True, если slug source_url содержит любой из запрещённых токенов.

    source_url — ссылка на карточку товара у источника (slug транслитерирован
    латиницей: .../product/kraska-dlya-drevesiny-...). exclusions —
    Material.category_exclusions (список подстрок-латиницы в нижнем регистре).

    Нет ссылки (seed/нет цены) или список пуст/не задан — считаем «свой» (False):
    без данных не помечаем, чтобы не пугать пользователя ложным флагом.
    """
    if not source_url or not exclusions:
        return False
    slug = source_url.lower()
    return any(token.lower() in slug for token in exclusions)
