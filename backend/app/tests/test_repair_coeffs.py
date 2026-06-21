# app/tests/test_repair_coeffs.py

import pytest
from decimal import Decimal
from app.services.repair_coeffs_service import apply_repair_coeffs, CONTINGENCY


class TestRepairCoeffs:

    def test_cosmetic_to_base_scale(self):
        """Проверка: косметический → базовый даёт рост ровно в 1.2 раза."""
        materials = {'min': Decimal('100'), 'avg': Decimal('200'), 'max': Decimal('300')}
        labor = {'min': Decimal('400'), 'avg': Decimal('500'), 'max': Decimal('600')}

        result_cosmetic = apply_repair_coeffs(materials, labor, 'cosmetic')
        result_base = apply_repair_coeffs(materials, labor, 'base')

        # Для каждой категории (materials, labor, total) и каждой границы (min, avg, max)
        for category in ['materials', 'labor', 'total']:
            for key in ['min', 'avg', 'max']:
                field = f'{category}_{key}'
                expected = result_cosmetic[field] * Decimal('1.2')
                assert result_base[field] == pytest.approx(expected, rel=1e-9)

    def test_min_avg_max_order(self):
        """Проверка: min ≤ avg ≤ max для всех категорий."""
        materials = {'min': Decimal('100'), 'avg': Decimal('200'), 'max': Decimal('300')}
        labor = {'min': Decimal('400'), 'avg': Decimal('500'), 'max': Decimal('600')}

        # Проверим для каждого типа ремонта
        for repair_type in ['cosmetic', 'base', 'extended']:
            result = apply_repair_coeffs(materials, labor, repair_type)
            for category in ['materials', 'labor', 'total']:
                min_val = result[f'{category}_min']
                avg_val = result[f'{category}_avg']
                max_val = result[f'{category}_max']
                assert min_val <= avg_val <= max_val, \
                    f"Для {category} не соблюдается min <= avg <= max: {min_val} <= {avg_val} <= {max_val}"

    def test_no_coeffs_equals_raw_sum(self):
        """Проверка: при косметическом ремонте и отсутствии непредвиденных (коэффициент = 1.0)
        итог равен чистой сумме материалов + работ."""
        materials = {'min': Decimal('100'), 'avg': Decimal('200'), 'max': Decimal('300')}
        labor = {'min': Decimal('400'), 'avg': Decimal('500'), 'max': Decimal('600')}

        result = apply_repair_coeffs(materials, labor, 'cosmetic')
        for key in ['min', 'avg', 'max']:
            mat_raw = materials[key]
            lab_raw = labor[key]
            raw_total = mat_raw + lab_raw

            # Делим результат на коэффициент непредвиденных и коэффициент типа (1.0)
            cont = CONTINGENCY[key]
            mat_final = result[f'materials_{key}'] / cont  # т.к. coeff=1.0
            lab_final = result[f'labor_{key}'] / cont
            total_final = result[f'total_{key}'] / cont

            assert mat_final == pytest.approx(mat_raw, rel=1e-9)
            assert lab_final == pytest.approx(lab_raw, rel=1e-9)
            assert total_final == pytest.approx(raw_total, rel=1e-9)

    def test_unknown_repair_type_raises_error(self):
        """Проверка, что неизвестный тип ремонта вызывает ValueError."""
        materials = {'min': Decimal('1'), 'avg': Decimal('2'), 'max': Decimal('3')}
        labor = {'min': Decimal('4'), 'avg': Decimal('5'), 'max': Decimal('6')}

        with pytest.raises(ValueError, match="Unknown repair_type: basic"):
            apply_repair_coeffs(materials, labor, 'basic')
