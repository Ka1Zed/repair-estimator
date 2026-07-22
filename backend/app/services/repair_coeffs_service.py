# app/services/repair_coeffs_service.py
#
# Классовый множитель ремонта (REPAIR_COEFFS/apply_repair_coeffs) убран (#222):
# объём работ задаётся составом works по каждой комнате, а не классом ремонта.
# Здесь остаётся только запас на непредвиденные расходы (вилка min/avg/max).

from decimal import Decimal

CONTINGENCY = {
    'min': Decimal('1.10'),
    'avg': Decimal('1.12'),
    'max': Decimal('1.15'),
}

# Коридор вилки ОДНОГО источника (estimation-rules.md, «Как складывается вилка»):
# при зафиксированном товаре/работе остаточный разброс цен — примерно −15%/+20%
# от средней. Каждый источник же отдаёт куда более широкий категорийный разброс
# (price-band: нижняя/верхняя треть цен категории, см. docs/price-sources.md),
# поэтому band КАЖДОГО источника прижимается к этому коридору вокруг ЕГО средней
# ДО объединения источников (#411, _combine_* в price_aggregator_service).
# Настоящая межисточниковая дисперсия (разные магазины/подрядчики реально расходятся
# в цене одной позиции) объединением НЕ клампится — она проходит в вилку как есть.
# Межтоварный разброс уровней (эконом/стандарт/премиум, #331) тоже коридором не
# ограничивается — он живёт в min_item/avg_item/max_item и выборе tier.
PRICE_CORRIDOR = {
    'min': Decimal('0.85'),
    'max': Decimal('1.20'),
}


def clamp_price_corridor(
    price_min: Decimal, price_avg: Decimal, price_max: Decimal,
) -> tuple[Decimal, Decimal]:
    """Прижимает band ОДНОГО источника к коридору вокруг его средней.

    Узкий band проходит как есть; категорийно-широкий (price-band целой категории
    в одной строке) обрезается до PRICE_CORRIDOR. Инвариант
    price_min ≤ price_avg ≤ price_max сохраняется. Применять к сырому band каждого
    источника ДО объединения (#411): межисточниковую дисперсию клампить нельзя.
    """
    lo = min(price_min, price_avg)
    hi = max(price_max, price_avg)
    return (
        max(lo, price_avg * PRICE_CORRIDOR['min']),
        min(hi, price_avg * PRICE_CORRIDOR['max']),
    )
