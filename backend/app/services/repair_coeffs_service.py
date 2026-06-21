from decimal import Decimal
from typing import Dict, Any

REPAIR_COEFFS = {
    'cosmetic': Decimal('1.0'),
    'base': Decimal('1.2'),
    'extended': Decimal('1.5'),
}

CONTINGENCY = {
    'min': Decimal('1.10'),
    'avg': Decimal('1.12'),
    'max': Decimal('1.15'),
}

def apply_repair_coeffs(
    materials: Dict[str, Any],
    labor: Dict[str, Any],
    repair_type: str
) -> Dict[str, Decimal]:
    """
    Применяет коэффициенты типа ремонта и непредвиденные расходы.
    """
    if repair_type not in REPAIR_COEFFS:
        raise ValueError(f"Unknown repair_type: {repair_type}. Allowed: cosmetic, base, extended")

    coeff = REPAIR_COEFFS[repair_type]
    result = {}

    for key in ['min', 'avg', 'max']:
        mat = Decimal(str(materials.get(key, 0)))   # приводим к Decimal
        lab = Decimal(str(labor.get(key, 0)))
        cont = CONTINGENCY[key]

        mat_final = mat * coeff * cont
        lab_final = lab * coeff * cont
        total = mat_final + lab_final

        result[f'materials_{key}'] = mat_final
        result[f'labor_{key}'] = lab_final
        result[f'total_{key}'] = total

    return result

