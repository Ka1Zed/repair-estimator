from typing import List, Optional
from pydantic import BaseModel, Field


class Point(BaseModel):
    x: float
    y: float

class Opening(BaseModel):
    type: str
    width: float
    height: float

class RoomInput(BaseModel):
    name: str
    height: float = Field(gt=0)
    points: List[Point] = Field(min_length=3)
    room_type: str
    openings: List[Opening] = []

class RepairOptions(BaseModel):
    floor: Optional[str] = None
    walls: Optional[str] = None
    ceiling: Optional[str] = None
    tile: Optional[bool] = False
    electric: Optional[str] = None
    plumbing: Optional[bool] = False

class EstimateRequest(BaseModel):
    city: str
    rooms: List[RoomInput]
    repair_type: str = Field(..., pattern="^(cosmetic|base|extended)$")
    repair_options: RepairOptions


class GeometrySummary(BaseModel):
    floor_area: float
    ceiling_area: float
    wall_area: float
    perimeter: float

class MaterialItem(BaseModel):
    name: str
    quantity: float
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
