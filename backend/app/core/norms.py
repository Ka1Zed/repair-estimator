# app/core/norms.py
#
# Глобальные (не привязанные к одному материалу) нормы расчёта, раньше
# захардкоженные внутри material_calc_service.py / geometry_service.py (#278).
# Источник значений — app/db/seed_data/norms.json; менять норму — правкой JSON,
# без правки .py. Материал-специфичные нормы (число слоёв, раппорт обоев)
# живут колонками на Material (см. seed_data/materials.json), не здесь.

import json
from decimal import Decimal
from pathlib import Path

_NORMS_PATH = Path(__file__).resolve().parent.parent / "db" / "seed_data" / "norms.json"

with open(_NORMS_PATH, "r", encoding="utf-8") as _f:
    _raw = json.load(_f)

# Кривизна основания под выравнивание → множитель расхода СТАРТОВОЙ шпаклёвки
# (норма 5.0 кг/м², вилка 3–8, см. estimation-rules.md). Финишную не трогает.
WALL_CONDITION_FACTOR: dict[str, Decimal] = {
    key: Decimal(str(value)) for key, value in _raw["wall_condition_factor"].items()
}

# Глубина откоса (толщина стены в проёме) по умолчанию, м — если проём не задал
# её явно (поле depth). Откосы отделываются отдельно и дороже стен (см. #191,
# docs/estimation-rules.md), поэтому в wall_area НЕ входят.
OTKOS_DEPTH_DEFAULT: dict[str, Decimal] = {
    key: Decimal(str(value)) for key, value in _raw["otkos_depth_default"].items()
}

# Высота вертикальной грани короба многоуровневого потолка на один уровень, м —
# дефолт для ceiling_shape.step_height_m, если не задан явно (#357).
CEILING_MULTILEVEL_STEP_HEIGHT_DEFAULT: Decimal = Decimal(
    str(_raw["ceiling_multilevel_step_height_default_m"])
)
