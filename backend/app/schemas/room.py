from pydantic import BaseModel
from typing import List

class Point(BaseModel):
    x: float
    y: float

class RoomCalculateRequest(BaseModel):
    points: List[Point]   # список вершин многоугольника
    height: float         # высота комнаты

class RoomCalculateResponse(BaseModel):
    floor_area: float
    ceiling_area: float
    perimeter: float
    wall_area: float