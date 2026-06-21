# app/schemas/estimate.py

from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, Field


# ---- Входные схемы ----
class Point(BaseModel):
    x: float
    y: float

class Opening(BaseModel):
    type: str  # "door" | "window"
    width: float
    height: float

class RoomInput(BaseModel):
    name: str
    height: float = Field(gt=0)
    points: List[Point] = Field(min_items=3)
    room_type: str  # "living", "bedroom", etc.
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


# ---- Выходные схемы ----
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
    updated_at: str  # YYYY-MM-DD

class LaborItem(BaseModel):
    service: str
    specialist: str
    volume: float
    unit: str
    price_avg: float
    total_avg: float
    source: str

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