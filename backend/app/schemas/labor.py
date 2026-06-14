from pydantic import BaseModel, ConfigDict


class LaborServiceOut(BaseModel):
    id: int
    name: str
    specialist_type: str
    unit: str

    model_config = ConfigDict(from_attributes=True)