# Backend-образ: FastAPI + uvicorn.
# poppler-utils нужен pdf2image для beta-распознавания PDF-чертежей (см. README).
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# При старте: миграции -> seed пустой БД -> дозасев непустой -> сервер.
# --if-empty засевает только пустую БД (не перетирает правки цен при рестарте).
# --missing идемпотентно добавляет новые позиции seed в непустую БД, НЕ трогая
# существующие цены (в т.ч. кэш парсеров) — так новые материалы/услуги из seed
# доезжают до прода при деплое без полного wipe-and-reseed.
# Готовность Postgres гарантирует depends_on healthcheck в docker-compose.
CMD ["sh", "-c", "alembic upgrade head && python -m app.db.seed --if-empty && python -m app.db.seed --missing && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
