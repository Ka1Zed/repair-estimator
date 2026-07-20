# app/tests/test_stats.py
# select_representative (#395): price_band_slice режет терцию строго по цене —
# выбор представителя ВНУТРИ терции раньше учитывал только близость к price_avg,
# package_size конкретной карточки никак не участвовал. Юнит-тесты ниже гоняют
# select_representative напрямую (без HTML/сети) на синтетических тройках
# (цена, метка, package_size).

from decimal import Decimal

from app.parsers._stats import select_representative


def test_select_representative_prefers_matching_package_size_on_price_tie():
    # avg=200, справочная фасовка=10. Цены A(190) и B(210) равноудалены от avg
    # (по 10) — раньше побеждал первый по порядку (A, фасовка 3, далеко от 10).
    # С учётом фасовки должен победить B — его package_size совпадает со
    # справочной.
    items = [
        (Decimal("190"), "a", Decimal("3")),
        (Decimal("210"), "b", Decimal("10")),
    ]

    rep = select_representative(
        items,
        price_avg=Decimal("200"),
        reference_package_size=Decimal("10"),
        price_key=lambda it: it[0],
        package_key=lambda it: it[2],
    )

    assert rep[1] == "b"


def test_select_representative_falls_back_to_price_only_without_reference():
    # reference_package_size=None — фасовка не учитывается, поведение как раньше.
    items = [
        (Decimal("190"), "a", Decimal("3")),
        (Decimal("210"), "b", Decimal("10")),
    ]

    rep = select_representative(
        items,
        price_avg=Decimal("200"),
        reference_package_size=None,
        price_key=lambda it: it[0],
        package_key=lambda it: it[2],
    )

    assert rep[1] == "a"


def test_select_representative_does_not_penalize_unknown_item_package_size():
    # У карточки package_size=None (сайт не показал второй ценовой блок) —
    # штрафа за фасовку нет, нечего сравнивать, решает только цена.
    items = [
        (Decimal("190"), "a", None),
        (Decimal("210"), "b", Decimal("50")),
    ]

    rep = select_representative(
        items,
        price_avg=Decimal("200"),
        reference_package_size=Decimal("10"),
        price_key=lambda it: it[0],
        package_key=lambda it: it[2],
    )

    assert rep[1] == "a"


def test_select_representative_picks_closer_price_when_package_size_equally_off():
    # Обе карточки одинаково далеко от справочной фасовки (10 ± 5) — решает цена.
    items = [
        (Decimal("195"), "a", Decimal("15")),
        (Decimal("230"), "b", Decimal("5")),
    ]

    rep = select_representative(
        items,
        price_avg=Decimal("200"),
        reference_package_size=Decimal("10"),
        price_key=lambda it: it[0],
        package_key=lambda it: it[2],
    )

    assert rep[1] == "a"
