# Локальная разработка

Как поднять проект для разработки на своей машине. Деплой на сервер — в
[deployment.md](deployment.md). Правила работы с ветками и PR —
в [contributing.md](contributing.md).

## Требования

- Docker и Docker Compose (для PostgreSQL)
- Python 3.12+ (backend)
- Node.js 20+ (frontend)
- Git

## Быстрый старт

```bash
git clone https://github.com/Ka1Zed/repair-estimator.git
cd repair-estimator
cp .env.example .env        # при необходимости поправить значения
docker compose up -d        # поднять PostgreSQL
```

Дальше — backend и frontend в отдельных терминалах (см. ниже).

## Backend

```bash
cd backend
python -m venv .venv

# Linux / macOS:
source .venv/bin/activate
# Windows (PowerShell):
.venv\Scripts\Activate.ps1

pip install -r requirements.txt

alembic upgrade head          # применить миграции БД
python -m app.db.seed         # стартовые данные (материалы, услуги, цены)
uvicorn app.main:app --reload # сервер разработки
```

- Backend: `http://localhost:8000`
- Health-check: `http://localhost:8000/health` → `{"status": "ok"}`
- Swagger: `http://localhost:8000/docs`

> **macOS на Apple Silicon (M1/M2/…).** Если `pytest`/`uvicorn` падают с
> `incompatible architecture (have 'arm64', need 'x86_64')`, значит venv создан
> x86_64-питоном под Rosetta, а колёса поставились arm64. Лечится пересозданием
> venv нативным питоном:
> ```bash
> rm -rf .venv && arch -arm64 python3 -m venv .venv && source .venv/bin/activate
> pip install -r requirements.txt
> ```
> Проверить разрядность активного питона: `python -c "import platform; print(platform.machine())"`.

### Переменные окружения

Все настройки берутся из `.env` (шаблон — `.env.example`):

| Переменная | Описание | Пример |
|---|---|---|
| `POSTGRES_USER` | Пользователь БД | `repair` |
| `POSTGRES_PASSWORD` | Пароль БД | `repair` |
| `POSTGRES_DB` | Имя базы | `repair_estimator` |
| `POSTGRES_HOST` | Хост БД | `localhost` |
| `POSTGRES_PORT` | Порт БД | `5432` |
| `GEMINI_API_KEY` | Ключ Google Gemini Vision для beta-загрузки чертежа (опц.) | — |
| `GEMINI_MODEL` | Модель Gemini для распознавания (опц.) | `gemini-2.5-flash` |
| `GEMINI_ENABLED` | Включить Gemini как fallback, если Claude недоступен; `false` — отключить совсем (опц.) | `true` |
| `ANTHROPIC_API_KEY` | Ключ Claude Vision — основной путь распознавания (опц.) | — |
| `ANTHROPIC_MODEL` | Модель Claude для распознавания (опц.) | `claude-sonnet-5` |
| `OLLAMA_BASE_URL` | URL локального Ollama для beta-загрузки чертежа (опц.) | `http://localhost:11434` |
| `BLUEPRINT_MAX_SIDE` | До скольких px ужимать чертёж перед распознаванием (опц.) | `2048` |
| `BLUEPRINT_TIMEOUT` | Таймаут ответа Gemini в секундах (опц.) | `90` |
| `MEGASTROY_COOKIE` | Cookie из браузера для обхода JS-проверки Мегастроя при `update_prices` (опц.) | `__ddg1_=...; PHPSESSID=...` |
| `MEGASTROY_UA` | User-Agent под эту cookie (опц., должен совпадать с браузером) | `Mozilla/5.0 ... YaBrowser/...` |

Ключи для распознавания чертежа необязательны: без них работает весь основной
сценарий (ручной 2D-ввод), beta-загрузка просто вернёт понятную ошибку.

`MEGASTROY_COOKIE`/`MEGASTROY_UA` нужны только для ручного прогона
`python -m app.manage update_prices`: сайт Мегастроя закрыт JS-проверкой
(DDoS-Guard) и отдаёт 403 на голый запрос. Обход — cookie hand-off: пройти
проверку в браузере, скопировать строку `Cookie` и `User-Agent` (DevTools →
Network → запрос документа → Request Headers) в эти переменные. Cookie живёт
недолго (привязана к IP+UA), при 403 — обновить. Если переменные пустые, расчёт
сметы не ломается: цена краски уходит на seed-fallback. Полный раннбук обновления
и проверки цен — [price-refresh.md](price-refresh.md).

### Beta: загрузка чертежа (системные зависимости)

Распознавание PDF-чертежей использует `pdf2image`, которому нужен системный
бинарь **poppler** (для PNG/JPG он не требуется):

- **macOS:** `brew install poppler`
- **Windows:** скачать [poppler для Windows](https://github.com/oschwartz10612/poppler-windows/releases),
  распаковать и добавить папку `bin` в `PATH`
- **Linux:** `sudo apt install poppler-utils`

Если poppler не установлен — PNG/JPG распознаются как обычно, а на PDF придёт
понятная ошибка вместо падения сервера.

### Тесты

```bash
cd backend
pytest
```

Тесты изолированы от dev-базы: они работают на отдельной БД
`repair_estimator_test` (имя можно переопределить переменной `POSTGRES_TEST_DB`).
`conftest.py` сам создаёт её при первом запуске, если её ещё нет — отдельная
ручная подготовка не нужна, достаточно поднятого PostgreSQL и прав на
`CREATE DATABASE`. Прогон `pytest` **не затирает** боевой seed в
`repair_estimator`, поэтому повторные запуски подряд не требуют пере-seed.

## Frontend

```bash
cd frontend
npm install        # первый раз или после изменения package.json
npm run dev        # сервер разработки
```

Frontend: `http://localhost:5173` (порт по умолчанию у Vite).

Адрес backend задаётся через переменную окружения Vite. Создать файл
`frontend/.env.local`:

```
VITE_API_URL=http://localhost:8000
```

Файл `.env.local` не коммитится — у каждого он свой. Шаблон лежит в
`frontend/.env.example`.

Полезные команды:

```bash
npm run dev        # сервер разработки с hot reload
npm run build      # production-сборка в папку dist/
npm run preview    # локальный просмотр production-сборки
npm run lint       # проверка кода линтером
```

## Работа с базой данных

```bash
# создать новую миграцию после изменения моделей
alembic revision --autogenerate -m "краткое описание изменения"

# применить миграции
alembic upgrade head

# откатить последнюю миграцию
alembic downgrade -1
```
