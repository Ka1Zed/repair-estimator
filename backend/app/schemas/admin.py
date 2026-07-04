from pydantic import BaseModel, model_validator
from decimal import Decimal


class PriceUpdateRequest(BaseModel):
    price_min: Decimal
    price_avg: Decimal
    price_max: Decimal
    region: str | None = None

    @model_validator(mode="after")
    def check_price_order(self) -> "PriceUpdateRequest":
        # Инвариант вилки: 0 < min ≤ avg ≤ max. Нарушение → 422 (не битая цена в БД).
        if not (0 < self.price_min <= self.price_avg <= self.price_max):
            raise ValueError("Цены должны удовлетворять 0 < price_min ≤ price_avg ≤ price_max")
        return self
