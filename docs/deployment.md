# Развёртывание на сервере

Весь стек (PostgreSQL + backend + frontend) поднимается **одной командой** через
Docker Compose — без ручной установки Python, Node и зависимостей на сервере.
Backend при старте сам применяет миграции и заливает seed-данные.

Локальная разработка — в [development.md](development.md).

## Что нужно на сервере

- Любой Linux-VPS (например Ubuntu 22.04+, от 1 ГБ RAM). Подойдёт бесплатный
  Google Cloud / Oracle Cloud Always Free или недорогой VPS (VDSina/Timeweb/Hetzner).
- Установленные Docker и Docker Compose plugin.
- Открытые порты `80` (сайт) и `8000` (API). Для HTTPS — ещё `443`
  (см. [https-setup.md](https-setup.md)).

> На инстансе с 1 ГБ RAM обязателен swap (≥ 2 ГБ), иначе сборка фронта падает по
> памяти. `deploy.sh` проверяет наличие swap перед выкаткой.

## Шаги

```bash
# 1. Установить Docker (Ubuntu)
curl -fsSL https://get.docker.com | sh

# 2. Забрать код
git clone https://github.com/Ka1Zed/repair-estimator.git
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

Отдельные шаги «по памяти» (venv, `pip install`, `alembic upgrade`,
`python -m app.db.seed`) на сервере не нужны — всё внутри контейнеров.

### Проверка

```bash
curl http://<адрес-сервера>:8000/health     # -> {"status":"ok"}
```

Сайт открывается на `http://<адрес-сервера>/`.

> Чтобы сайт работал по `https://` с валидным сертификатом (без покупки домена,
> через Caddy + sslip.io) — см. [https-setup.md](https-setup.md).

### Зачем две переменные адреса

Frontend — это статика, собранная заранее, поэтому адрес backend
(`VITE_API_URL`) **зашивается в бандл** на этапе `docker compose build`.
`FRONTEND_URL` нужен backend для CORS — он разрешает запросы только с адреса
сайта. Обе должны указывать на реальный адрес сервера, иначе браузер упрётся в
CORS или будет стучаться в `localhost`. После смены адреса пересобрать фронт:
`docker compose up -d --build`.

> Seed выполняется только при пустой БД (`--if-empty`): первый запуск заливает
> стартовые данные, а при рестартах и обновлениях контейнера ранее накопленные
> данные (в т.ч. правки цен) не перетираются. Контейнеры подняты с
> `restart: unless-stopped` — стек сам поднимется после перезагрузки сервера.

## Обновление и обслуживание

Выкатка новой версии — одним скриптом из корня репозитория на сервере:

```bash
./deploy.sh            # выкатить main (по умолчанию): pull → пересборка → проверка health
./deploy.sh dev        # выкатить другую ветку
```

Скрипт проверяет наличие `.env` и swap, не затирает локальные правки трекаемых
файлов и дожидается зелёного `GET /health`. Под капотом — то же, что вручную:

```bash
git pull && docker compose up -d --build   # выкатить новую версию
docker compose logs -f backend             # логи backend
docker compose ps                          # статус контейнеров
docker compose down                        # остановить (данные БД в volume сохранятся)
```
