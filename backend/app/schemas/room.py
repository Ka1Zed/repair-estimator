from pydantic import BaseModel, Field, field_validator
from typing import List

class Point(BaseModel):
    x: float
    y: float

class RoomCalculateRequest(BaseModel):
    height: float = Field(..., gt=0)
    points: List[Point] = Field(..., min_length=3)

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