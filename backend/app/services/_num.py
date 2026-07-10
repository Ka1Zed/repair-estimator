# app/services/_num.py
#
# Общий числовой хелпер calc-сервисов (был продублирован в material_calc_service.py,
# labor_calc_service.py и hidden_works_service.py — #278).

from decimal import Decimal


def D(value) -> Decimal:
    """Безопасное приведение к Decimal (поля БД — float, геометрия — float)."""
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal(0)
    return Decimal(str(value))
