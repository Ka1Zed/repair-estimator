"""Юнит-тесты матчера смежной категории (#406)."""
from app.services.category_match import detect_category_mismatch


def test_mismatch_when_slug_has_excluded_token():
    # Живой пример из issue: под «Краска потолочная» резолвится «краска для
    # древесины» — slug содержит запрещённый токен → помечаем несоответствие.
    url = "https://kazan.leman.ru/product/kraska-dlya-drevesiny-parade-carnelian-123"
    assert detect_category_mismatch(url, ["drevesin", "po-metall", "fasad"]) is True


def test_no_mismatch_for_own_product():
    url = "https://kazan.leman.ru/product/kraska-potolochnaya-parade-w1-9l-456"
    assert detect_category_mismatch(url, ["drevesin", "po-metall", "fasad"]) is False


def test_case_insensitive():
    url = "https://x/PRODUCT/Kraska-Dlya-Drevesiny-789"
    assert detect_category_mismatch(url, ["DREVESIN"]) is True


def test_no_url_or_no_exclusions_is_false():
    # Seed/нет цены (source_url=None) или материал без списка — не помечаем.
    assert detect_category_mismatch(None, ["drevesin"]) is False
    assert detect_category_mismatch("https://x/kraska-dlya-drevesiny", None) is False
    assert detect_category_mismatch("https://x/kraska-dlya-drevesiny", []) is False


def test_wide_honest_category_not_flagged():
    # Плитка честно широкая (359→4637 ₽) и токенов смежных категорий у неё нет —
    # ложных срабатываний быть не должно.
    url = "https://kazan.megastroy.com/products/plitka-keramicheskaya-mramor-60x60"
    assert detect_category_mismatch(url, None) is False


def test_multi_surface_paint_not_flagged_under_ceiling():
    # #406: типовой товар «краска для стен и потолков» под потолочной — это НЕ
    # смежная категория (годится и на потолок). Токен `dlya-sten` убран, чтобы
    # такой slug не давал ложного срабатывания.
    url = "https://kazan.leman.ru/product/kraska-dlya-sten-i-potolkov-parade-w1-9l-2"
    ceiling_tokens = ["drevesin", "dereva", "derevu", "po-metall", "po-metallu",
                      "fasad", "avtomobil", "dlya-pola"]
    assert detect_category_mismatch(url, ceiling_tokens) is False


def test_only_product_slug_is_checked():
    # Токен ищется в slug'е карточки, а не во всём URL: совпадение в домене/пути
    # (город/каталог) не должно давать флаг.
    url = "https://fasad-city.megastroy.com/catalog/fasadnye/kraska-potolochnaya-w1-9l"
    assert detect_category_mismatch(url, ["fasad"]) is False


def test_token_matches_only_on_word_boundary():
    # Токен на границе слова слага; внутри чужого слова — не считается.
    assert detect_category_mismatch("https://x/kraska-dlya-drevesiny", ["drevesin"]) is True
    assert detect_category_mismatch("https://x/nedrevesin-kraska", ["drevesin"]) is False
