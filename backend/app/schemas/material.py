from pydantic import BaseModel, ConfigDict


class MaterialOut(BaseModel):
    id: int
    name: str
    category: str
    unit: str
    package_size: float | None

    model_config = ConfigDict(from_attributes=True)