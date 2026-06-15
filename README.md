# Repair Estimator — калькулятор стоимости ремонта

Веб-приложение, которое по заданной форме и размерам помещения рассчитывает примерную стоимость ремонта: площадь и периметр, необходимые материалы, нужных специалистов и итоговую вилку стоимости (минимум / средняя / максимум). Результат — полная смета: что купить, в каком количестве и по какой цене, а также какие работы и сколько они стоят.

## Идея проекта

Пользователь:

1. задаёт помещение как 2D-многоугольник (вручную через редактор или таблицу точек);
2. указывает высоту потолка, двери и окна;
3. выбирает тип ремонта (косметический / базовый / расширенный) и набор работ (пол, стены, потолок, плитка, электрика, сантехника).

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

### Тесты backend

```bash
cd backend
pytest
```

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

​```bash
git checkout dev
git pull
git checkout -b feature/моя-задача
​```

Первые две строки (`checkout dev` + `pull`) обязательны **каждый раз**. Если создать ветку от `main` или от устаревшего `dev`, то: PR будет уходить не в ту ветку, не подтянется свежий код коллег, и при слиянии возникнут конфликты и дубли.

### 2. `node_modules` и сборки НИКОГДА не коммитим

Папка `node_modules/` содержит сотни тысяч файлов — её коммит раздувает PR до сотен тысяч строк и ломает ревью. Она уже прописана в `.gitignore`, git её игнорирует автоматически. **Не добавляй её принудительно.**

Если `node_modules` всё же попал в git, убрать так:

​```bash
git rm -r --cached node_modules
git commit -m "chore: remove node_modules from tracking"
​```

Перед коммитом всегда полезно глянуть `git status` и убедиться, что в изменениях только твои файлы.

### 3. Код живёт строго в своих папках

- Frontend — **только** в `frontend/`. Команды (`npm install`, `npm run dev`, `npm run build`) запускаются из папки `frontend/`, а не из корня.
- Backend — **только** в `backend/`.

Если запускать `npm install` в корне, там появится лишний `node_modules` и дубликат проекта. Перед работой над фронтом: `cd frontend`.

### 4. PR открывать в `dev`, не в `main`

При создании Pull Request проверь селектор веток вверху: **base должен быть `dev`**, compare — твоя ветка.

### 5. Перед пушем — быстрая самопроверка

​```bash
# backend:
ruff check .
pytest
# frontend:
npm run build
​```

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
