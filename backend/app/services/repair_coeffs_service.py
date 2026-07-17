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

# Коридор вилки внутри уровня (estimation-rules.md, «Как складывается вилка»):
# при зафиксированном товаре/работе остаточный разброс цен — примерно −15%/+20%
# от средней. Источники же отдают куда более широкий категорийный разброс
# (price-band: нижняя/верхняя треть цен категории, см. docs/price-sources.md),
# поэтому границы каждой строки прижимаются к этому коридору при расчёте.
# Межтоварный разброс уровней (эконом/стандарт/премиум, #331) коридором не
# ограничивается — он живёт в min_item/avg_item/max_item и выборе tier.
PRICE_CORRIDOR = {
    'min': Decimal('0.85'),
    'max': Decimal('1.20'),
}


def clamp_price_corridor(
    price_min: Decimal, price_avg: Decimal, price_max: Decimal,
) -> tuple[Decimal, Decimal]:
    """Прижимает границы вилки цены к коридору вокруг средней.

    Узкая вилка проходит как есть; категорийно-широкая обрезается до
    PRICE_CORRIDOR. Инвариант price_min ≤ price_avg ≤ price_max сохраняется.
    """
    lo = min(price_min, price_avg)
    hi = max(price_max, price_avg)
    return (
        max(lo, price_avg * PRICE_CORRIDOR['min']),
        min(hi, price_avg * PRICE_CORRIDOR['max']),
    )
