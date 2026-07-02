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
