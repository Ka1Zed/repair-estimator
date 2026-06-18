from pydantic import BaseModel, Field, field_validator
from typing import List, Optional

class Point(BaseModel):
    x: float
    y: float

class Opening(BaseModel):
    type: str = Field(..., description="Тип проёма: door / window")
    width: float = Field(..., gt=0, description="Ширина в метрах")
    height: float = Field(..., gt=0, description="Высота в метрах")

    @field_validator('type')
    def validate_type(cls, v):
        if v not in ('door', 'window'):
            raise ValueError('type must be "door" or "window"')
        return v

class RoomCalculateRequest(BaseModel):
    height: float = Field(..., gt=0)
    points: List[Point] = Field(..., min_length=3)
    openings: List[Opening] = Field(default_factory=list, description="Список проёмов (двери/окна)")

    @field_validator('height')
    def height_positive(cls, v):
        if v <= 0:
            raise ValueError('height must be greater than 0')
        return v

    @field_validator('points')
    def points_min_length(cls, v):
        if len(v) < 3:
            raise ValueError('points must contain at least 3 items')
        return v

class RoomCalculateResponse(BaseModel):
    floor_area: float
    ceiling_area: float
    perimeter: float
    wall_area: float