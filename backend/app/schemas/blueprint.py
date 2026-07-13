from pydantic import BaseModel, Field
from typing import List, Optional, Literal


class Point(BaseModel):
    x: float
    y: float
    nx: Optional[float] = None
    ny: Optional[float] = None


class Opening(BaseModel):
    """Проем (дверь или окно)"""
    type: Literal["door", "window"]
    width: float
    height: float
    position: Optional[Point] = None  # позиция на плане (опционально)


class BlueprintUploadResponse(BaseModel):
    """Результат распознавания чертежа"""
    success: bool
    method: Literal["gemini", "claude", "ollama", "ocr", "fixture", "none"]  # используемый метод
    confidence: float = Field(..., ge=0, le=1, description="Уверенность в результате (0-1)")

    # Извлеченные данные
    points: List[Point] = Field(default_factory=list, description="Углы помещения")
    height: Optional[float] = Field(None, description="Высота потолка в метрах")
    openings: List[Opening] = Field(default_factory=list, description="Двери и окна")

    # Метаданные для пользователя
    raw_dimensions: List[str] = Field(
        default_factory=list,
        description="Найденные размеры в исходном виде"
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Предупреждения о проблемах распознавания"
    )
