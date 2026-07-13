from datetime import datetime
from typing import List, Literal

from pydantic import BaseModel, Field

from app.schemas.estimate import RoomInput


class ProjectCreate(BaseModel):
    name: str
    city: str
    rooms: List[RoomInput] = Field(min_length=1)
    scope: Literal["finish_only", "rough_and_finish", "rough_only"] = "finish_only"


class ProjectUpdate(ProjectCreate):
    """Полная замена плана проекта (PUT) — те же поля, что и при создании."""


class ProjectListItem(BaseModel):
    """Лёгкая карточка проекта для списка — без rooms и share_token."""
    id: int
    name: str
    city: str
    created_at: datetime
    updated_at: datetime


class ProjectResponse(ProjectListItem):
    """Полный ответ владельцу: план + share_token для ссылки-шеринга."""
    rooms: List[RoomInput]
    scope: str
    share_token: str


class ProjectShareResponse(BaseModel):
    """Публичный read-only ответ по share-токену — без id и share_token."""
    name: str
    city: str
    rooms: List[RoomInput]
    scope: str
    created_at: datetime
    updated_at: datetime
