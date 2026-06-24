"""Тесты разбора/нормализации beta-распознавания чертежей.

Сеть и vision-модели не дёргаются — проверяем только пост-обработку:
масштаб из размеров рёбер, нормализованные координаты, fallback и валидацию.
Claude-путь проверяется с замоканным SDK-клиентом (без ключа и сети).
"""
import sys
import types
from unittest.mock import MagicMock

from PIL import Image

from app.services.blueprint_service import BlueprintService

RECT = [
    {"x": 100, "y": 100},
    {"x": 500, "y": 100},
    {"x": 500, "y": 400},
    {"x": 100, "y": 400},
]


def _svc():
    return BlueprintService()


def test_scale_derived_from_edges_gives_metric_points():
    """Размеры рёбер прочитаны → x/y в метрах считаются сами, без калибровки."""
    data = {
        "corners_px": RECT,
        "edge_dimensions": [
            {"from_index": 0, "to_index": 1, "length_m": 4.0},  # 400px
            {"from_index": 1, "to_index": 2, "length_m": 3.0},  # 300px
        ],
        "ceiling_height_m": 2.7,
    }
    r = _svc()._normalize_extract(data, (800, 600))
    assert r["success"] is True
    assert r["points"][0]["x"] == 0.0 and r["points"][0]["y"] == 0.0
    assert abs(r["points"][1]["x"] - 4.0) < 0.01
    assert abs(r["points"][2]["y"] - 3.0) < 0.01
    assert r["height"] == 2.7
    # масштаб найден → нет предупреждения о калибровке
    assert not any("калибру" in w.lower() for w in r["warnings"])


def test_normalized_coords_relative_to_image():
    r = _svc()._normalize_extract({"corners_px": RECT}, (800, 600))
    assert r["points"][0]["nx"] == 0.125  # 100/800
    assert r["points"][0]["ny"] == round(100 / 600, 4)


def test_no_dimensions_falls_back_to_manual_calibration():
    """Размеры не прочитаны → x/y=0 и предупреждение, фронт уйдёт в калибровку."""
    r = _svc()._normalize_extract({"corners_px": RECT, "edge_dimensions": []}, (800, 600))
    assert r["success"] is True  # контур есть, оверлей покажем
    assert r["points"][1]["x"] == 0.0
    assert any("калибру" in w.lower() for w in r["warnings"])


def test_inconsistent_edges_use_median():
    """Один кривой размер не должен ломать масштаб — берём медиану."""
    data = {
        "corners_px": RECT,
        "edge_dimensions": [
            {"from_index": 0, "to_index": 1, "length_m": 4.0},   # 0.01 m/px
            {"from_index": 1, "to_index": 2, "length_m": 3.0},   # 0.01 m/px
            {"from_index": 2, "to_index": 3, "length_m": 40.0},  # выброс 0.1 m/px
        ],
    }
    mpp = _svc()._scale_from_edges(data["edge_dimensions"], RECT)
    assert abs(mpp - 0.01) < 1e-6


def test_fewer_than_three_corners_not_success():
    r = _svc()._normalize_extract({"corners_px": RECT[:2]}, (800, 600))
    assert r["success"] is False
    assert any("контур" in w.lower() for w in r["warnings"])


def test_garbage_input_does_not_crash():
    r = _svc()._normalize_extract({}, (800, 600))
    assert r["success"] is False
    assert r["points"] == []


def test_openings_accept_metric_keys():
    data = {
        "corners_px": RECT,
        "openings": [
            {"type": "door", "width_m": 0.9, "height_m": 2.0},
            {"type": "window", "width_m": 1.4, "height_m": 1.2},
            {"type": "wall", "width_m": 1.0, "height_m": 1.0},  # мусорный тип — отброс
        ],
    }
    r = _svc()._normalize_extract(data, (800, 600))
    assert len(r["openings"]) == 2
    assert r["openings"][0] == {"type": "door", "width": 0.9, "height": 2.0}


def test_height_out_of_range_dropped():
    assert _svc()._validate_height(0.5) is None
    assert _svc()._validate_height(2.7) == 2.7
    assert _svc()._validate_height(99) is None


def test_extract_json_handles_markdown_fences():
    svc = _svc()
    assert svc._extract_json('```json\n{"corners_px": []}\n```') == {"corners_px": []}
    assert svc._extract_json('prefix {"a": 1} suffix') == {"a": 1}
    assert svc._extract_json("no json here") == {}


def test_claude_path_with_mocked_sdk(monkeypatch):
    """Полная цепочка Claude (вызов → парсинг → нормализация) с замоканным SDK.

    Проверяет: используется ANTHROPIC_MODEL, берётся первый текстовый блок
    (а не content[0]), JSON в ```-блоке парсится, метры считаются из размеров.
    """
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

    captured = {}

    # Ответ Claude: сначала thinking-блок, потом текст с JSON в markdown-обёртке.
    thinking_block = types.SimpleNamespace(type="thinking", thinking="...")
    text_block = types.SimpleNamespace(
        type="text",
        text='```json\n{"corners_px": ['
             '{"x":100,"y":100},{"x":500,"y":100},{"x":500,"y":400},{"x":100,"y":400}],'
             '"edge_dimensions":[{"from_index":0,"to_index":1,"length_m":4.0},'
             '{"from_index":1,"to_index":2,"length_m":3.0}],'
             '"ceiling_height_m":2.7,"openings":[],"raw_dimensions":["4000","3000"],"notes":[]}\n```',
    )
    fake_response = types.SimpleNamespace(content=[thinking_block, text_block])

    fake_client = MagicMock()

    def _create(**kwargs):
        captured.update(kwargs)
        return fake_response

    fake_client.messages.create.side_effect = _create
    fake_anthropic = types.ModuleType("anthropic")
    fake_anthropic.Anthropic = MagicMock(return_value=fake_client)
    monkeypatch.setitem(sys.modules, "anthropic", fake_anthropic)

    svc = BlueprintService()
    svc.anthropic_key = "test-key"
    r = svc._process_with_claude(Image.new("RGB", (800, 600)))

    assert captured["model"] == "claude-sonnet-4-6"
    assert r["method"] == "claude"
    assert r["success"] is True
    assert abs(r["points"][1]["x"] - 4.0) < 0.01
    assert abs(r["points"][2]["y"] - 3.0) < 0.01
    assert r["height"] == 2.7
