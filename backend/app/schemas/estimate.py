from typing import List, Optional
from pydantic import BaseModel, Field


class Point(BaseModel):
    x: float
    y: float

class Opening(BaseModel):
    type: str
    width: float
    height: float


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

class RoomInput(BaseModel):
    name: str
    height: float = Field(gt=0)
    points: List[Point] = Field(min_length=3)
    # room_type — пресет дефолтов, не констрейнт (бэкенд works не валидирует по нему).
    room_type: str
    openings: List[Opening] = []
    works: Works = Field(default_factory=Works)

class EstimateRequest(BaseModel):
    city: str
    rooms: List[RoomInput]


class GeometrySummary(BaseModel):
    floor_area: float
    ceiling_area: float
    wall_area: float
    perimeter: float

class MaterialItem(BaseModel):
    name: str
    quantity: float
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
    price_avg: float
    total_avg: float
    source: str
    # Ссылка на карточку/категорию товара у источника цены: задана для парсерных
    # цен, null для seed и для позиций без цены. Фронт (F2-8) делает из неё ссылку.
    source_url: Optional[str] = None
    updated_at: str
    # Регион, по которому реально взялась цена: город при региональной seed-цене
    # или null, если цена базовая (region IS NULL) / парсерная. См. city в запросе.
    region: Optional[str] = None

class LaborItem(BaseModel):
    service: str
    specialist: str
    volume: float
    unit: str
    price_avg: float
    total_avg: float
    source: str
    # Ссылка на страницу услуги у источника цены: задана для парсерных цен, null для seed.
    source_url: Optional[str] = None
    region: Optional[str] = None
    # Все сайты, чьи цены объединены в эту вилку (#166). Для одного источника —
    # один элемент; для seed-цены — null. В строке сметы source — представительный
    # сайт (его средняя ближе к итоговой), а sources — полный список через запятую.
    sources: Optional[List[str]] = None

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
    summary: Summary
    geometry: GeometrySummary
    materials: List[MaterialItem]
    labor: List[LaborItem]
