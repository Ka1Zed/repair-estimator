# app/services/repair_coeffs_service.py
#
# B1-3: Применение коэффициентов типа ремонта и непредвиденных расходов
# к итоговым суммам материалов и работ.
#
# Используется на этапе агрегации (B1-5) для формирования финальной вилки стоимости.

from decimal import Decimal
from typing import Dict

# Коэффициенты типа ремонта (из задания)
REPAIR_COEFFS = {
    'cosmetic': Decimal('1.0'),
    'base': Decimal('1.2'),
    'extended': Decimal('1.5'),
}

# Непредвиденные расходы для каждой границы вилки
CONTINGENCY = {
    'min': Decimal('1.10'),   # +10%
    'avg': Decimal('1.12'),   # +12%
    'max': Decimal('1.15'),   # +15%
}


def apply_repair_coeffs(
    materials: Dict[str, Decimal],
    labor: Dict[str, Decimal],
    repair_type: str
) -> Dict[str, Decimal]:
    """
    Применяет коэффициенты типа ремонта и непредвиденные расходы к суммам материалов и работ.

    Параметры:
        materials: словарь с ключами 'min', 'avg', 'max' – суммы материалов (без учёта коэффициентов)
        labor: словарь с ключами 'min', 'avg', 'max' – суммы работ (без учёта коэффициентов)
        repair_type: 'cosmetic' | 'base' | 'extended'

    Возвращает:
        словарь с ключами:
            materials_min, materials_avg, materials_max,
            labor_min, labor_avg, labor_max,
            total_min, total_avg, total_max
    """
    coeff = REPAIR_COEFFS.get(repair_type, Decimal('1.0'))
    result = {}

    for key in ['min', 'avg', 'max']:
        mat = materials.get(key, Decimal(0))
        lab = labor.get(key, Decimal(0))
        cont = CONTINGENCY[key]

        mat_final = mat * coeff * cont
        lab_final = lab * coeff * cont
        total = mat_final + lab_final

        result[f'materials_{key}'] = mat_final
        result[f'labor_{key}'] = lab_final
        result[f'total_{key}'] = total

    return result