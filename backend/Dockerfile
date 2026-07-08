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

# При старте: миграции -> seed пустой БД -> пере-калибровка непустой -> сервер.
# --if-empty засевает только пустую БД (не перетирает правки цен при рестарте).
# --refresh-seed-prices (#282) идемпотентно дозасевает новые позиции seed (как
# было у --missing) И ДОПОЛНИТЕЛЬНО обновляет уже существующие source='seed'
# строки значениями из seed_data — так рекалибровка цен (напр. #213) доезжает
# до непустого прода на каждом деплое. Кэш парсеров и не-seed цены не трогает.
# Готовность Postgres гарантирует depends_on healthcheck в docker-compose.
CMD ["sh", "-c", "alembic upgrade head && python -m app.db.seed --if-empty && python -m app.db.seed --refresh-seed-prices && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
