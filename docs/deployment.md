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
> данные (в т.ч. правки цен) не перетираются. Следом контейнер прогоняет
> `python -m app.db.seed --missing` — идемпотентный **дозасев**: добавляет новые
> позиции из `seed_data/*.json` (материалы/услуги/источники и их seed-цены), не
> трогая существующие цены. Так новые данные seed доезжают до прода при деплое
> **без** wipe-and-reseed. Контейнеры подняты с `restart: unless-stopped` — стек
> сам поднимется после перезагрузки сервера.
>
> ⚠️ **Никогда не запускай на проде голый `python -m app.db.seed`** (без флага):
> это полный wipe-and-reseed — `.delete()` по всем ценам и заливка только
> seed-данных, что **затрёт кэш парсеров** (`update_prices`). Новые позиции seed
> добавляет `--missing`. Если полный ре-seed всё же неизбежен — сразу после него
> прогнать `python -m app.manage update_prices` (см. [price-refresh.md](price-refresh.md)),
> чтобы восстановить цены парсеров поверх seed.

> **Пере-калибровка seed-цен.** `--missing` цены существующих позиций не апдейтит,
> поэтому изменения цен в `seed_data/*.json` (напр. рекалибровка #213) сами на прод
> не доезжают. Когда правил именно seed-цены — после выкатки прогнать один раз:
>
> ```bash
> docker compose exec backend python -m app.db.seed --refresh-seed-prices
> ```
>
> Режим делает UPDATE строк с `source='seed'` значениями из `seed_data/*.json` и
> дозасевает недостающие позиции; цены **других** источников (кэш парсеров,
> региональные не-seed) не трогает. Идемпотентен — повторный прогон ничего не меняет.

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

## Резервные копии БД

Кэш парсерных цен (`update_prices`) и правки региональных цен живут только в
docker-volume `postgres_data`. Потеря диска e2-micro = потеря всего собранного —
поэтому нужен регулярный дамп.

`backup.sh` (в корне репозитория, рядом с `deploy.sh`) делает сжатый дамп через
`pg_dump` **внутри** контейнера и стримит его в gzip на хост — без промежуточных
файлов и тяжёлых инструментов, чтобы уложиться в 1 ГБ RAM. БД при этом только
читается.

```bash
./backup.sh                 # дамп в ./backups/, ротация — 7 суток
KEEP_DAYS=14 ./backup.sh    # хранить дольше
BACKUP_DIR=/mnt/x ./backup.sh
```

Имя файла — `repair_estimator-YYYYmmdd-HHMMSS.sql.gz`. Каталог `backups/` в
`.gitignore` — дампы в репозиторий не попадают. Битый или пустой архив скрипт
удаляет и завершает с ошибкой, так что «зелёный» выход = валидная копия.

### Ежедневный запуск (cron)

Дамп раз в сутки в 03:30. Открыть `crontab -e` и добавить строку (путь — под свой
логин; `>>` копит лог, куда пишутся и ошибки):

```cron
30 3 * * * cd /home/<логин>/repair-estimator && ./backup.sh >> /home/<логин>/backup.log 2>&1
```

Проверить, что задание на месте: `crontab -l`. Первый прогон лучше сделать руками
(`./backup.sh`) и убедиться, что в `backups/` появился непустой `.sql.gz`.

> Дампы лежат на том же диске, что и БД. Для защиты от потери самого инстанса
> периодически забирайте свежий файл с сервера, например:
> `scp <логин>@<адрес-сервера>:~/repair-estimator/backups/<файл>.sql.gz .`
> (или `gsutil cp` в GCS-бакет).

### Восстановление

Дамп — это обычный SQL (плюс gzip), заливается через `psql` в контейнере.
`.sql.gz` от `pg_dump` содержит только данные и схему, но **не** пересоздаёт саму
БД, поэтому таблицы перед заливкой надо очистить.

```bash
# 1. Остановить backend, чтобы никто не писал в БД во время восстановления.
docker compose stop backend

# 2. Пересоздать пустую схему (сотрёт текущие данные БД!).
docker compose exec -T postgres psql -U repair -d repair_estimator \
  -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

# 3. Залить дамп (подставь нужный файл).
gunzip -c backups/repair_estimator-YYYYmmdd-HHMMSS.sql.gz \
  | docker compose exec -T postgres psql -U repair -d repair_estimator

# 4. Поднять backend обратно.
docker compose start backend
```

Имя пользователя/БД (`repair` / `repair_estimator`) — из `.env`
(`POSTGRES_USER` / `POSTGRES_DB`). После восстановления проверить health:
`curl http://localhost:8000/health`.
