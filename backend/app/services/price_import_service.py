import csv
import io
import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from app.db.session import SessionLocal
from app.db.models import (
    Material, MaterialPrice, LaborService, LaborPrice, PriceSource
)

logger = logging.getLogger(__name__)


def import_prices_from_csv(csv_text: str, source_name: str = "manual") -> dict:
    # source_name — имя источника в price_sources (manual / avito / ...)
    session = SessionLocal()
    try:
        src = session.query(PriceSource).filter(
            PriceSource.name == source_name
        ).first()
        if not src:
            raise RuntimeError(f"Источник '{source_name}' не найден в БД (нужен seed price_sources)")
        # дальше везде, где было manual_source, используем src

        reader = csv.DictReader(io.StringIO(csv_text))
        updated = 0
        skipped = []

        for i, row in enumerate(reader, start=2):  # start=2: строка 1 — заголовок
            kind = (row.get("kind") or "").strip().lower()
            name = (row.get("name") or "").strip()

            if not name or kind not in ("material", "labor"):
                skipped.append(f"строка {i}: некорректные kind/name")
                continue

            # парсим цены
            try:
                price_min = Decimal(row["price_min"])
                price_avg = Decimal(row["price_avg"])
                price_max = Decimal(row["price_max"])
            except (KeyError, InvalidOperation, TypeError):
                skipped.append(f"строка {i} ('{name}'): не разобрал цены")
                continue

            now = datetime.now(timezone.utc)

            if kind == "material":
                entity = session.query(Material).filter(Material.name == name).first()
                if not entity:
                    skipped.append(f"строка {i}: материал '{name}' не найден")
                    continue
                price = session.query(MaterialPrice).filter(
                    MaterialPrice.material_id == entity.id,
                    MaterialPrice.source_id == src.id
                ).first()
                if not price:
                    price = MaterialPrice(material_id=entity.id, source_id=src.id)
                    session.add(price)

            else:  # labor
                entity = session.query(LaborService).filter(LaborService.name == name).first()
                if not entity:
                    skipped.append(f"строка {i}: услуга '{name}' не найдена")
                    continue
                price = session.query(LaborPrice).filter(
                    LaborPrice.labor_service_id == entity.id,
                    LaborPrice.source_id == src.id
                ).first()
                if not price:
                    price = LaborPrice(labor_service_id=entity.id, source_id=src.id)
                    session.add(price)

            price.price_min = price_min
            price.price_avg = price_avg
            price.price_max = price_max
            price.updated_at = now
            updated += 1

        session.commit()
        logger.info(f"Импорт завершён. Обновлено: {updated}, пропущено: {len(skipped)}")
        return {"updated": updated, "skipped": skipped}

    finally:
        session.close()


def import_prices_from_file(path: str, source_name: str = "manual") -> dict:
    with open(path, encoding="utf-8") as f:
        return import_prices_from_csv(f.read(), source_name=source_name)