# app/tests/test_parser_registry.py
# Реестр источников цен (#294): манифест, из которого manage.py/estimates.py
# читают список парсеров, а не хардкодят его сами.

from app.parsers.base import BaseParser
from app.parsers.registry import BASE_LABOR_PARSER, MATERIAL_PARSERS, REGIONAL_LABOR_PARSERS


def test_material_parsers_non_empty_and_named():
    assert MATERIAL_PARSERS
    for parser in MATERIAL_PARSERS:
        assert isinstance(parser, BaseParser)
        assert parser.source_name
        assert parser.known_materials(), f"{parser.source_name}: пустой список материалов"


def test_regional_labor_parsers_have_region_and_source():
    assert REGIONAL_LABOR_PARSERS
    for parser in REGIONAL_LABOR_PARSERS:
        assert isinstance(parser, BaseParser)
        assert parser.source_name
        assert parser.region


def test_base_labor_parser_is_configured():
    assert isinstance(BASE_LABOR_PARSER, BaseParser)
    assert BASE_LABOR_PARSER.source_name
