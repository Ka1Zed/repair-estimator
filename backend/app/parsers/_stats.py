"""Общие статистические хелперы для парсеров цен."""

import statistics
from decimal import Decimal


def filter_outliers(items: list, key=lambda x: x) -> list:
    # Отсев ценовых выбросов методом Тьюки (1.5·IQR). Одна категория/услуга мешает
    # разнородные позиции: у Мегастроя — грунты по ~175 ₽ и дизайнерские краски по
    # ~15000 ₽ (#207), у парсеров работ — мелкие операции (розетка 180 ₽) и нишевые
    # дорогие работы (7500 ₽) под одной услугой (#242). Без отсева региональная
    # вилка раздувалась в разы. Считаем квартили по ценам методом `inclusive`
    # (numpy-совместимая линейная интерполяция) и оставляем позиции в пределах
    # [Q1−1.5·IQR, Q3+1.5·IQR]. `inclusive` (в отличие от дефолтного `exclusive`)
    # уверенно режет одиночный дорогой выброс уже на малых прайсах в 5 строк —
    # ровно на примере из #242 [400, 500, 550, 600, 7000]; на объёмных выборках
    # оба метода совпадают. `key` достаёт цену из элемента: у LaborTableParser и
    # Megastroy это пара (цена, url), у Rembrigada — сама цена. Источник-
    # представитель (#166/#197) затем выбирается уже из отфильтрованного набора.
    if len(items) < 4:
        # На малой выборке (< 4) квартили бессмысленны — оставляем как есть.
        return items
    prices = sorted(key(it) for it in items)
    q1, _, q3 = statistics.quantiles(prices, n=4, method="inclusive")
    iqr = q3 - q1
    lo = q1 - Decimal("1.5") * iqr
    hi = q3 + Decimal("1.5") * iqr
    filtered = [it for it in items if lo <= key(it) <= hi]
    # Защита от вырождения (все цены равны → iqr=0 → отсекать нечего): если фильтр
    # вдруг всё выкинул, откатываемся к исходной выборке — цена не должна пропасть
    # и уйти в seed из-за фильтра (#242).
    return filtered or items


def filter_undersized_packages(items: list, key, reference_package_size: Decimal | None) -> list:
    """Отсеивает карточки с нетиповой (мелкой) фасовкой перед агрегацией цены (#382).

    У кг/л-материалов (шпаклёвка, клей, затирка, грунтовка) категория обычно содержит
    больше карточек мелкой фасовки (3-5 кг), чем мешков/канистр (25-30 кг) — без этого
    фильтра price_avg и товар-представитель (ближайший к avg) съезжают к цене мелкой
    фасовки, хотя типовая закупка — мешками. key(item) -> Decimal | None (package_size
    конкретной карточки); карточка без известной фасовки (None) не отсеивается — про
    неё нечего сказать. Порог — треть от справочной Material.package_size.

    reference_package_size is None (материал без справочной фасовки) — фильтр no-op.
    В отличие от filter_outliers, пустой результат НЕ откатывается к исходной выборке:
    если вся категория — нетиповая фасовка, типового представителя нет, и это должно
    вести к seed-fallback у вызывающего кода, а не к неверной цене.
    """
    if reference_package_size is None or reference_package_size <= 0:
        return items
    threshold = reference_package_size / 3
    return [it for it in items if key(it) is None or key(it) >= threshold]


def select_representative(
    items: list,
    price_avg: Decimal,
    reference_package_size: Decimal | None,
    price_key=lambda x: x[0],
    package_key=lambda x: None,
):
    """Выбирает товар-представитель (источник цены и package_size) внутри уже
    отрезанной price_band-терции (#395).

    До этой функции представитель выбирался только по ближайшей к price_avg
    цене — package_size конкретной карточки в отборе не участвовал. У ходовых
    фасовок (например, банка 5 л) цена, ближайшая к avg, часто оказывается и в
    нижней, и в верхней терции — эконом и премиум-варианты получали одну и ту
    же фасовку, хотя тир должен различать не только цену, но и упаковку.

    Комбинируем ОТНОСИТЕЛЬНЫЕ (безразмерные, поэтому сравнимые между собой)
    отклонения цены от price_avg и package_size от reference_package_size —
    карточка с "нетипичной" фасовкой, но чуть более близкой ценой, больше не
    выигрывает автоматически. reference_package_size или package_size
    конкретной карточки неизвестны (None) — вклад фасовки в скор = 0 (нечего
    сравнивать, откатываемся к чистой цене, как и раньше).
    """
    def score(item) -> Decimal:
        price = price_key(item)
        price_dist = abs(price - price_avg) / price_avg if price_avg else Decimal(0)
        package_size = package_key(item)
        if reference_package_size and package_size:
            package_dist = abs(package_size - reference_package_size) / reference_package_size
        else:
            package_dist = Decimal(0)
        return price_dist + package_dist

    return min(items, key=score)


def price_band_slice(items: list, band: str, key=lambda x: x) -> list:
    """Режет уже отфильтрованную (filter_outliers) выборку на терции по цене (#331).

    Мегастрой/Леман не дают надёжных фасетов «бренд/класс» на уровне всех
    категорий (кроме краски — там есть facet стена/потолок) — вместо этого
    приближаем эконом/премиум-варианты долей самой дешёвой/дорогой трети уже
    найденных в категории товаров. `band`: "low" (эконом) — нижняя треть,
    "high" (премиум) — верхняя треть; любое другое значение — вся выборка
    без изменений (соответствует стандартному tier=avg).

    На малой выборке (< 3, треть выродилась бы в пустоту) возвращаем всё как
    есть — цена не должна пропасть только из-за банда (тот же принцип, что и
    защита от вырождения в filter_outliers).
    """
    if band not in ("low", "high") or len(items) < 3:
        return items
    ordered = sorted(items, key=key)
    third = max(1, len(ordered) // 3)
    return ordered[:third] if band == "low" else ordered[-third:]
