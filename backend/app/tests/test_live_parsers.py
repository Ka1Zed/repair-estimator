# app/tests/test_live_parsers.py
# Реальные сетевые смоук-проверки парсеров (#174). Ходят в живой Мегастрой, поэтому
# помечены @pytest.mark.live и исключены из обычного прогона (addopts = -m "not live").
# Запуск вручную при наличии сети: pytest -m live

import pytest

from app.parsers.megastroy_parser import MegastroyParser

pytestmark = pytest.mark.live


def test_megastroy_returns_positive_price_for_paint():
    """Живой Мегастрой отдаёт валидную вилку цен для краски (min ≤ avg ≤ max, все > 0)."""
    parsed = MegastroyParser().fetch_price("Краска для стен")

    assert parsed is not None
    assert parsed.price_min > 0
    assert parsed.price_avg > 0
    assert parsed.price_max > 0
    assert parsed.price_min <= parsed.price_avg <= parsed.price_max
