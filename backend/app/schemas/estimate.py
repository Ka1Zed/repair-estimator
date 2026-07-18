from typing import List, Literal, Optional
from pydantic import BaseModel, Field, field_validator

from app.core.regions import normalize_city


class Point(BaseModel):
    x: float
    y: float

class Opening(BaseModel):
    type: str
    width: float
    height: float
    # Глубина откоса (толщина стены в проёме), м. null → дефолт по типу проёма
    # (дверь/окно, см. geometry_service.OTKOS_DEPTH_DEFAULT). Влияет на площадь
    # откосов, не на wall_area. См. docs/estimation-rules.md.
    depth: Optional[float] = Field(None, gt=0)


class SurfaceWork(BaseModel):
    """Отделка поверхности (пол/стены/потолок). См. works в docs/api.md."""
    enabled: bool = False
    # Ключ отделки из finishOptions.<группа> в room-types.json; null — поверхность
    # включена, но отделка ещё не выбрана.
    finish: Optional[str] = None
    # Обои под рисунок (раппорт): +30% к расходу рулонов на подгонку (только стены).
    # См. estimation-rules.md.
    wallpaper_pattern: Optional[bool] = False
    # Пористое/сильно впитывающее основание: грунтовка в 2 слоя вместо 1.
    # См. estimation-rules.md.
    primer_two_coats: Optional[bool] = False
    # Состояние/кривизна основания под выравнивание (even/normal/uneven):
    # масштабирует расход только стартовой шпаклёвки. См. estimation-rules.md.
    wall_condition: Optional[str] = None
    # Натяжной потолок (#191, только ceiling.finish="stretch"): число закладных
    # под светильники (точки потолочника). null → дефолт светильников типа комнаты.
    light_points: Optional[int] = Field(None, ge=0)
    # Натяжной потолок: погонаж ниши под карниз/штору, м. null/0 → ниши нет.
    curtain_niche_m: Optional[float] = Field(None, ge=0)

class ElectricWork(BaseModel):
    """Электрика комнаты. Числа опциональны: при null бэкенд ставит дефолт от площади."""
    enabled: bool = False
    sockets: Optional[int] = None
    lights: Optional[int] = None
    cable_m: Optional[float] = None

class PlumbingWork(BaseModel):
    """Сантехника комнаты. Числа опциональны: при null бэкенд ставит дефолт от типа/площади."""
    enabled: bool = False
    points: Optional[int] = None
    pipe_m: Optional[float] = None

class Works(BaseModel):
    """Работы и их настройки на уровне комнаты (см. docs/api.md)."""
    floor: SurfaceWork = Field(default_factory=SurfaceWork)
    walls: SurfaceWork = Field(default_factory=SurfaceWork)
    ceiling: SurfaceWork = Field(default_factory=SurfaceWork)
    electric: ElectricWork = Field(default_factory=ElectricWork)
    plumbing: PlumbingWork = Field(default_factory=PlumbingWork)

class CeilingShape(BaseModel):
    """Форма потолка (#357): по умолчанию плоский, ceiling_area = floor_area.

    multilevel — многоуровневый ГКЛ-потолок: добавляет площадь вертикальных
    граней коробов по периметру помещения на каждый уровень (levels ×
    step_height_m). attic_slope — мансардный скат: единая наклонная
    плоскость над проекцией пола (floor_area / cos(slope_deg)).
    """
    type: Literal["flat", "multilevel", "attic_slope"] = "flat"
    levels: Optional[int] = Field(None, ge=1, le=5)
    step_height_m: Optional[float] = Field(None, gt=0, le=1.0)
    slope_deg: Optional[float] = Field(None, ge=0, lt=85)

class RoomInput(BaseModel):
    name: str
    height: float = Field(gt=0)
    points: List[Point] = Field(min_length=3)
    # room_type — пресет дефолтов, не констрейнт (бэкенд works не валидирует по нему).
    room_type: str
    openings: List[Opening] = []
    works: Works = Field(default_factory=Works)
    # Форма потолка (#357), null — плоский (прежнее поведение, ceiling_area = floor_area).
    ceiling_shape: Optional[CeilingShape] = None

class EstimateRequest(BaseModel):
    # Валидируется/нормализуется против SUPPORTED_CITIES (#394): неизвестный
    # город (опечатка, «Питер» вместо «Санкт-Петербург») — явный 422, а не
    # тихий откат на дефолтные источники (Мегастрой + Леман-Казань). Регистр/
    # пробелы игнорируются — «москва» и «Москва» матчят один регион.
    city: str
    rooms: List[RoomInput]
    tier: str = Field("avg", pattern="^(min|avg|max)$")  # уровень комплектации
    # Стадийность сметы (#190, #303). finish_only (дефолт) — только чистовая отделка;
    # rough_and_finish — черновая + чистовая; rough_only — черновая + предчистовая,
    # БЕЗ чистовой отделки и её материалов (ремонт под чистовую сдачу). Класса ремонта
    # в контракте нет (#222) — объём задаётся составом works, а глубину сметы — scope.
    scope: Literal["finish_only", "rough_and_finish", "rough_only"] = "finish_only"
    # Явный выбор магазина(ов) материалов (#363, напр. ["Леман"]) — см. GET
    # /api/regions/stores для списка магазинов и их доступности по city. Сужает
    # источники цен материалов до перечисленных; null/[] — прежний автоподбор по
    # covered_cities. Если выбранный магазин известен системе, но не покрывает
    # city — тихий откат на автоподбор (расчёт не падает и не остаётся без цены).
    # Если имя магазина не найдено СРЕДИ ЗАРЕГИСТРИРОВАННЫХ вовсе (опечатка) —
    # 422, а не тихий откат (проверка в calculate_estimate).
    stores: Optional[List[str]] = None

    @field_validator("city")
    @classmethod
    def validate_city(cls, v: str) -> str:
        return normalize_city(v)


class GeometrySummary(BaseModel):
    floor_area: float
    ceiling_area: float
    wall_area: float
    perimeter: float

class MaterialTierItem(BaseModel):
    """Товар конкретного уровня комплектации внутри MaterialItem.*_item (#349).

    Для finish_key-позиций (ламинат, покраска стен/потолка, плитка, обои, розетка —
    #331) min/avg/max — РАЗНЫЕ SKU (свои name/source_url) — эконом/стандарт/премиум.
    Для остальных материалов (один товар на все tier) — совпадают между собой и со
    значениями строки. quantity общая с родительской строкой (не пересчитывается по
    норме расхода конкретного SKU) — только price/total и атрибуция источника меняются.
    """
    name: str
    price: float
    total: float
    source: str
    source_url: Optional[str] = None

class MaterialItem(BaseModel):
    name: str
    quantity: float
    # Уровень комплектации (min/avg/max) — эхо запроса
    tier: str  # "min" | "avg" | "max"
    # Цена за единицу для выбранного уровня
    price: float
    # Итог для выбранного уровня
    total: float
    # Полная вилка (min/avg/max) для отображения коридора
    price_min: float
    price_avg: float
    price_max: float
    total_min: float
    total_avg: float
    total_max: float
    # Из чего складывается quantity (#176): base_quantity — площадь/длина × норма
    # расхода, ДО запаса; waste_factor — применённый коэффициент запаса
    # (совмещает waste_factor материала и, для обоев под рисунок, раппорт);
    # base_quantity × waste_factor == quantity ДО округления до упаковок.
    base_quantity: float
    waste_factor: float
    package_size: float
    # Число упаковок, до которого округлили: packs × package_size == quantity.
    packs: int
    unit: str
    source: str
    # Ссылка на карточку/категорию товара у источника цены: задана для парсерных
    # цен, null для seed и для позиций без цены. Фронт (F2-8) делает из неё ссылку.
    source_url: Optional[str] = None
    updated_at: str
    # Регион, по которому реально взялась цена: город при региональной seed-цене
    # или null, если цена базовая (region IS NULL) / парсерная. См. city в запросе.
    region: Optional[str] = None
    # Все источники, чьи цены объединены в эту вилку (#333, по аналогии с LaborItem.sources).
    # Для одного источника — один элемент; для seed-цены — null. source/source_url —
    # представительный источник (его средняя ближе к итоговой).
    sources: Optional[List[str]] = None
    # Источник границы вилки (#348), если он отличается от представителя (source/source_url):
    # чья строка реально дала price_min/price_max при объединении нескольких источников.
    # null, если источник один или граница совпадает с представителем (не дублируем ссылку).
    min_source: Optional[str] = None
    min_source_url: Optional[str] = None
    max_source: Optional[str] = None
    max_source_url: Optional[str] = None
    # SKU-варианты по уровню комплектации (#349) — избавляют фронт от 3× запроса
    # /calculate (tier=min/avg/max) ради имён/ссылок альтернативных товаров.
    # Для finish_key-позиций разные (эконом/стандарт/премиум), иначе совпадают.
    min_item: MaterialTierItem
    avg_item: MaterialTierItem
    max_item: MaterialTierItem

class LaborItem(BaseModel):
    service: str
    specialist: str
    # Стадия работы (#190): rough (черновая) / pre_finish (предчистовая) /
    # finish (чистовая). Классифицирует строку по этапу ремонта, чтобы фронт
    # мог сгруппировать смету и пользователь не принял финиш за полную смету.
    stage: Literal["rough", "pre_finish", "finish"]
    volume: float
    unit: str
    # Уровень комплектации (min/avg/max) — эхо запроса
    tier: str  # "min" | "avg" | "max"
    # Цена за единицу для выбранного уровня
    price: float
    # Итог для выбранного уровня
    total: float
    # Полная вилка (min/avg/max) для отображения коридора
    price_min: float
    price_avg: float
    price_max: float
    total_min: float
    total_avg: float
    total_max: float
    source: str
    updated_at: str
    # Ссылка на страницу услуги у источника цены: задана для парсерных цен, null для seed.
    source_url: Optional[str] = None
    region: Optional[str] = None
    # Все сайты, чьи цены объединены в эту вилку (#166). Для одного источника —
    # один элемент; для seed-цены — null. В строке сметы source — представительный
    # сайт (его средняя ближе к итоговой), а sources — полный список через запятую.
    sources: Optional[List[str]] = None
    # Источник границы вилки (#348), если он отличается от представителя (source/source_url):
    # чей сайт реально дал price_min/price_max при объединении нескольких сайтов.
    # null, если источник один или граница совпадает с представителем.
    min_source: Optional[str] = None
    min_source_url: Optional[str] = None
    max_source: Optional[str] = None
    max_source_url: Optional[str] = None

class HiddenWorkItem(BaseModel):
    """Строка блока «может всплыть доплатой» (#239).

    Скрытая работа — типовой сюрприз под старой отделкой (доп. демонтаж, замена
    стяжки, штробы в бетоне и т.п.), который заранее не оценить. Вилка ориентировочная
    и НЕ входит в summary основной сметы — см. HiddenWorks.note.
    """
    service: str
    specialist: str
    # Почему работа может всплыть — короткое пояснение для пользователя.
    reason: str
    # Ориентировочный объём (по геометрии сценария); цены за единицу — из seed-работ.
    volume: float
    unit: str
    price_avg: float
    # Ориентировочная вилка по строке (volume × цена min/avg/max), справочно.
    total_min: float
    total_avg: float
    total_max: float
    source: str

class HiddenWorks(BaseModel):
    """Блок скрытых работ (#239): возможные доплаты, НЕ входящие в summary.

    Отдаётся всегда; items пуст, если для сценария нет типовых скрытых работ.
    Суммы блока (total_*) — справочные и намеренно не смешиваются с summary основной сметы.
    """
    # Явная пометка для фронта/пользователя, что блок вне итоговой сметы.
    note: str
    total_min: float
    total_avg: float
    total_max: float
    items: List[HiddenWorkItem]

class Summary(BaseModel):
    materials_min: float
    materials_avg: float
    materials_max: float
    labor_min: float
    labor_avg: float
    labor_max: float
    total_min: float
    total_avg: float
    total_max: float

class EstimateResponse(BaseModel):
    # Эхо запрошенной стадийности (#190). finish_only — смета покрывает только
    # чистовую отделку (без черновых работ); это ЯВНО помечено, чтобы пользователь
    # не принял финиш за полную смету капремонта (черновые = 40–60% сметы).
    scope: str
    summary: Summary
    geometry: GeometrySummary
    materials: List[MaterialItem]
    labor: List[LaborItem]
    # Блок «может всплыть доплатой» (#239): типовые скрытые работы сценария с
    # ориентировочной вилкой. НЕ входит в summary — см. HiddenWorks.note.
    hidden_works: HiddenWorks
