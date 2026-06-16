from pydantic import BaseModel
from decimal import Decimal


class PriceUpdateRequest(BaseModel):
    price_min: Decimal
    price_avg: Decimal
    price_max: Decimal
    region: str | None = None