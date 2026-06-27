# Repair Estimator — калькулятор стоимости ремонта

Веб-приложение, которое по заданной форме и размерам помещения рассчитывает примерную стоимость ремонта: площадь и периметр, необходимые материалы, нужных специалистов и итоговую вилку стоимости (минимум / средняя / максимум). Результат — полная смета: что купить, в каком количестве и по какой цене, а также какие работы и сколько они стоят.

## Идея проекта

Пользователь:

1. задаёт помещение как 2D-многоугольник (вручную через редактор или таблицу точек);
2. указывает высоту потолка, двери и окна;
3. выбирает класс ремонта (косметический / капитальный / дизайнерский) и набор работ (пол, стены, потолок, плитка, электрика, сантехника).

Система считает:

- площадь пола, потолка, стен и периметр;
- количество материалов по нормам расхода;
- стоимость материалов и работ специалистов;
- итоговую вилку: минимум / средняя / максимум;
- детальную смету: таблица закупки и таблица работ с указанием источника цены и даты обновления.

Загрузка чертежа с распознаванием размеров — **дополнительная beta-функция**: система пытается извлечь размеры, пользователь обязательно подтверждает и правит результат вручную. Основной сценарий MVP — ручной 2D-ввод.

## Команда и роли

| Роль | Зона ответственности |
|---|---|
| Frontend 1 | Редактор помещения: страница создания проекта, 2D-редактор многоугольника, ввод точек, высоты потолка, дверей и окон |
| Frontend 2 | Интерфейс сметы: страница результата, таблицы материалов и работ, итоговая стоимость, загрузка чертежа, экспорт, отображение источников цен |
| Backend 1 | Расчёты: геометрия (площадь, периметр, стены), расчёт материалов и работ, итоговая смета, тесты расчётной логики |
| Backend 2 | Данные и цены: БД, модели, миграции, seed-данные, источники цен, парсеры/импорт цен, кэширование, Docker, CI |

## Стек технологий

- **Frontend:** React + TypeScript + Vite, Zustand, SVG/Konva для 2D-редактора
- **Backend:** Python, FastAPI, SQLAlchemy, Alembic, pytest
- **БД:** PostgreSQL
- **Инфраструктура:** Docker Compose, GitHub Actions

## Структура проекта

```
repair-estimator/
  frontend/             # React-приложение
  backend/              # FastAPI-приложение
    app/
      api/              # endpoint'ы (rooms, estimates, materials, labor, uploads)
      core/             # конфигурация
      db/               # модели, сессия, миграции
      services/         # geometry, estimate, materials, labor, price aggregator
      parsers/          # парсеры/импортёры цен
      schemas/          # Pydantic-схемы запросов/ответов
      tests/            # тесты
  docker-compose.yml
  .env.example
  README.md
  docs/
    api.md              # API-контракт frontend ↔ backend
    architecture.md
    estimation-rules.md # нормы расхода материалов и формулы расчёта
```

## Требования для запуска

- Docker и Docker Compose (для PostgreSQL)
- Python 3.12+ (для backend)
- Node.js 20+ (для frontend)
- Git

## Быстрый старт

```bash
git clone <url-репозитория>
cd repair-estimator
cp .env.example .env        # при необходимости поправить значения
docker compose up -d        # поднять PostgreSQL
```

## Запуск backend

```bash
cd backend
python -m venv .venv

# Linux / macOS:
source .venv/bin/activate
# Windows (PowerShell):
.venv\Scripts\Activate.ps1

pip install -r requirements.txt

# применить миграции БД
alembic upgrade head

# > macOS на Apple Silicon (M1/M2/...): если pytest/uvicorn падают с
# > `incompatible architecture (have 'arm64', need 'x86_64')`, значит venv
# > создан x86_64-питоном под Rosetta, а колёса поставились arm64. Лечится
# > пересозданием venv нативным питоном:
# >   rm -rf .venv && arch -arm64 python3 -m venv .venv && source .venv/bin/activate
# >   pip install -r requirements.txt
# > Проверить разрядность активного питона: `python -c "import platform; print(platform.machine())"`

# заполнить базу стартовыми данными (материалы, услуги, цены)
python -m app.db.seed

# запустить сервер разработки
uvicorn app.main:app --reload
```

Backend будет доступен на `http://localhost:8000`.

Проверка работоспособности: открыть `http://localhost:8000/health` — должен вернуться `{"status": "ok"}`.

Автодокументация API (Swagger): `http://localhost:8000/docs`.

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
| `GEMINI_ENABLED` | Включить Gemini; `false` — использовать Claude (опц.) | `true` |
| `ANTHROPIC_API_KEY` | Ключ Claude Vision для beta-загрузки чертежа (опц.) | — |
| `ANTHROPIC_MODEL` | Модель Claude для распознавания (опц.) | `claude-sonnet-4-6` |
| `OLLAMA_BASE_URL` | URL локального Ollama для beta-загрузки чертежа (опц.) | `http://localhost:11434` |
| `BLUEPRINT_MAX_SIDE` | До скольких px ужимать чертёж перед распознаванием (опц.) | `2048` |
| `BLUEPRINT_TIMEOUT` | Таймаут ответа Gemini в секундах (опц.) | `90` |

Ключи для распознавания чертежа необязательны: без них работает весь основной
сценарий (ручной 2D-ввод), beta-загрузка просто вернёт понятную ошибку.

### Beta: загрузка чертежа (системные зависимости)

Распознавание PDF-чертежей использует `pdf2image`, которому нужен системный
бинарь **poppler** (для PNG/JPG он не требуется):

- **macOS:** `brew install poppler`
- **Windows:** скачать [poppler для Windows](https://github.com/oschwartz10612/poppler-windows/releases),
  распаковать и добавить папку `bin` в `PATH`
- **Linux:** `sudo apt install poppler-utils`

Если poppler не установлен — PNG/JPG распознаются как обычно, а на PDF придёт
понятная ошибка вместо падения сервера.

### Тесты backend

```bash
cd backend
pytest
```

Тесты изолированы от dev-базы: они работают на отдельной БД
`repair_estimator_test` (имя можно переопределить переменной `POSTGRES_TEST_DB`).
`conftest.py` сам создаёт её при первом запуске, если её ещё нет — отдельная
ручная подготовка не нужна, достаточно поднятого PostgreSQL и прав на
`CREATE DATABASE`. Прогон `pytest` больше **не затирает** боевой seed в
`repair_estimator`, поэтому повторные запуски подряд не требуют пере-seed.

## Запуск frontend

```bash
cd frontend
npm install        # установить зависимости (первый раз или после изменения package.json)
npm run dev        # запустить сервер разработки
```

Frontend будет доступен на `http://localhost:5173` (порт по умолчанию у Vite).

Адрес backend задаётся через переменную окружения Vite. Создать файл `frontend/.env.local`:

```
VITE_API_URL=http://localhost:8000
```

Файл `.env.local` не коммитится в репозиторий — у каждого он свой. Шаблон лежит в `frontend/.env.example`.

### Полезные команды frontend

```bash
npm run dev        # сервер разработки с hot reload
npm run build      # production-сборка в папку dist/
npm run preview    # локальный просмотр production-сборки
npm run lint       # проверка кода линтером
```

## Развёртывание на удалённом сервере

Весь стек (PostgreSQL + backend + frontend) поднимается **одной командой** через Docker Compose — без ручной установки Python, Node и зависимостей на сервере. Backend при старте сам применяет миграции и заливает seed-данные.

### Что нужно на сервере

- Любой Linux-VPS (например Ubuntu 22.04+, от 1 ГБ RAM). Подойдёт бесплатный Oracle Cloud Always Free или недорогой VPS (VDSina/Timeweb/Hetzner).
- Установленные Docker и Docker Compose plugin.
- Открытые порты `80` (сайт) и `8000` (API).

### Шаги

```bash
# 1. Установить Docker (Ubuntu)
curl -fsSL https://get.docker.com | sh

# 2. Забрать код
git clone <url-репозитория>
cd repair-estimator

# 3. Настроить окружение
cp .env.example .env
# В .env обязательно поправить под адрес сервера (IP или домен) и сменить пароль БД:
#   FRONTEND_URL=http://<адрес-сервера>
#   VITE_API_URL=http://<адрес-сервера>:8000
#   POSTGRES_PASSWORD=<свой-пароль>

# 4. Собрать и поднять весь стек в фоне
docker compose up -d --build
```

Отдельные шаги «по памяти» (venv, `pip install`, `alembic upgrade`, `python -m app.db.seed`) на сервере не нужны — всё внутри контейнеров.

### Проверка

```bash
curl http://<адрес-сервера>:8000/health     # -> {"status":"ok"}
```

Сайт открывается на `http://<адрес-сервера>/`.

### Зачем две переменные адреса

Frontend — это статика, собранная заранее, поэтому адрес backend (`VITE_API_URL`) **зашивается в бандл** на этапе `docker compose build`. `FRONTEND_URL` нужен backend для CORS — он разрешает запросы только с адреса сайта. Обе должны указывать на реальный адрес сервера, иначе браузер упрётся в CORS или будет стучаться в `localhost`. После смены адреса пересобрать фронт: `docker compose up -d --build`.

> Seed выполняется только при пустой БД (`--if-empty`): первый запуск заливает стартовые данные, а при рестартах и обновлениях контейнера ранее накопленные данные (в т.ч. правки цен) не перетираются. Контейнеры подняты с `restart: unless-stopped` — стек сам поднимется после перезагрузки сервера.

### Обновление и обслуживание

```bash
git pull && docker compose up -d --build   # выкатить новую версию
docker compose logs -f backend             # логи backend
docker compose ps                          # статус контейнеров
docker compose down                        # остановить (данные БД в volume сохранятся)
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

## Важные правила (чтобы не ломать репозиторий)

Несколько правил, которые экономят команде часы на разгребании проблем. Прочитать **до** начала работы.

### 1. Ветку всегда создавать от свежего `dev`

```bash
git checkout dev
git pull
git checkout -b feature/моя-задача
```

Первые две строки (`checkout dev` + `pull`) обязательны **каждый раз**. Если создать ветку от `main` или от устаревшего `dev`, то: PR будет уходить не в ту ветку, не подтянется свежий код коллег, и при слиянии возникнут конфликты и дубли.

### 2. `node_modules` и сборки НИКОГДА не коммитим

Папка `node_modules/` содержит сотни тысяч файлов — её коммит раздувает PR до сотен тысяч строк и ломает ревью. Она уже прописана в `.gitignore`, поэтому git её игнорирует автоматически. **Не добавляй её принудительно** и не делай `git add` для неё.

Если `node_modules` всё же попал в git (например, был закоммичен раньше), убрать так:

```bash
git rm -r --cached node_modules
git commit -m "chore: remove node_modules from tracking"
```

Перед коммитом всегда полезно глянуть `git status` и убедиться, что в изменениях только твои файлы, а не тысячи служебных.

### 3. Код живёт строго в своих папках

- Frontend — **только** в `frontend/`. Команды (`npm install`, `npm run dev`, `npm run build`) запускаются из папки `frontend/`, а не из корня репозитория.
- Backend — **только** в `backend/`.

Если запускать `npm install` в корне, там появится лишний `node_modules` и дубликат проекта, который конфликтует с `frontend/`. Перед работой над фронтом: `cd frontend`.

### 4. PR открывать в `dev`, не в `main`

При создании Pull Request на GitHub проверь селектор веток вверху: **base должен быть `dev`**, compare — твоя ветка. В `main` напрямую идёт только финальная сборка недели.

### 5. Перед пушем — быстрая самопроверка

```bash
# backend:
ruff check .          # линтер не должен ругаться
pytest                # тесты проходят

# frontend:
npm run build         # сборка проходит без ошибок TypeScript
```

CI всё равно это проверит, но поймать локально быстрее, чем ждать красный CI на PR.

## Git workflow

### Ветки

- `main` — только стабильная версия. Напрямую в `main` никто не пушит.
- `dev` — общая ветка разработки.
- `feature/...` — ветки под задачи (например `feature/backend-geometry-service`).
- `fix/...` — ветки с исправлениями багов.
- `docs/...` — ветки с документацией.

### Процесс работы над задачей

1. Взять issue из GitHub Project Board.
2. Создать feature-ветку от `dev`.
3. Сделать задачу, проверить локально.
4. Открыть Pull Request в `dev` по шаблону.
5. Получить review минимум от одного человека.
6. Влить в `dev`.
7. В конце недели стабильный `dev` вливается в `main` и помечается тегом (`v0.1-week1`, `v0.2-week2`, ...).

### Формат коммитов

```
feat: add polygon area calculation
fix: correct wall area formula
docs: update api contract
refactor: split estimate service
test: add geometry tests
```

## Основные команды

| Команда | Что делает |
|---|---|
| `docker compose up -d` | Поднять PostgreSQL (и остальные сервисы) в фоне |
| `docker compose down` | Остановить контейнеры |
| `docker compose logs -f postgres` | Логи базы данных |
| `uvicorn app.main:app --reload` | Запустить backend локально |
| `pytest` | Прогнать тесты backend |
| `alembic upgrade head` | Применить миграции |
| `npm run dev` | Запустить frontend локально |

## Документация

- [API-контракт](docs/api.md) — формат запросов и ответов между frontend и backend
- [Архитектура](docs/architecture.md)
- [Правила расчёта сметы](docs/estimation-rules.md)

## Ограничения MVP

В первую версию сознательно **не входят**: BIM/CAD, идеальное автораспознавание чертежей, 3D-визуализация, авторизация с ролями, оплата, маркетплейс специалистов, мобильное приложение. Загрузка чертежа — экспериментальная beta-функция с обязательным ручным подтверждением размеров.
