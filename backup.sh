#!/usr/bin/env bash
#
# backup.sh — резервная копия прод-БД PostgreSQL (ежедневный дамп).
#
# Запускать НА сервере из корня репозитория (рядом с deploy.sh):
#   ./backup.sh                 # дамп в ./backups/, ротация — 7 дней
#   BACKUP_DIR=/mnt/x ./backup.sh   # свой каталог
#   KEEP_DAYS=14 ./backup.sh        # хранить дольше
#
# Лёгкий по памяти: pg_dump внутри контейнера стримит SQL сразу в gzip, без
# промежуточных файлов и тяжёлых инструментов — годится для e2-micro (1ГБ RAM).
# БД не меняется: pg_dump — только чтение.
#
# Восстановление и настройка cron — в docs/deployment.md, раздел «Резервные копии БД».

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
KEEP_DAYS="${KEEP_DAYS:-7}"

# 0. Запуск из корня репозитория (рядом должен лежать docker-compose.yml).
if [ ! -f docker-compose.yml ]; then
  echo "✗ docker-compose.yml не найден. Запускай скрипт из корня репозитория." >&2
  exit 1
fi

# 1. .env обязателен — из него берём имя пользователя и БД для pg_dump.
if [ ! -f .env ]; then
  echo "✗ .env не найден. Нужны POSTGRES_USER/POSTGRES_DB для pg_dump." >&2
  exit 1
fi

# Значение переменной из .env (последнее вхождение): терпит пробелы вокруг '='
# (KEY = value), обрезает их по краям и снимает окружающие кавычки.
db_env() {
  local line v
  line="$(grep -E "^[[:space:]]*${1}[[:space:]]*=" .env | tail -n1)" || return 0
  v="${line#*=}"
  v="${v#"${v%%[![:space:]]*}"}"   # обрезать ведущие пробелы
  v="${v%"${v##*[![:space:]]}"}"   # обрезать хвостовые пробелы
  v="${v%\"}"; v="${v#\"}"
  v="${v%\'}"; v="${v#\'}"
  printf '%s' "$v"
}
DB_USER="$(db_env POSTGRES_USER)"; : "${DB_USER:=repair}"
DB_NAME="$(db_env POSTGRES_DB)";   : "${DB_NAME:=repair_estimator}"

mkdir -p "$BACKUP_DIR"

TS="$(date +%Y%m%d-%H%M%S)"
OUT="${BACKUP_DIR}/${DB_NAME}-${TS}.sql.gz"

# 2. Дамп: pg_dump в контейнере → gzip на хосте. pipefail поймает падение pg_dump.
echo "→ Дамп БД '${DB_NAME}' → ${OUT}…"
if ! docker compose exec -T postgres pg_dump -U "$DB_USER" "$DB_NAME" | gzip -c > "$OUT"; then
  echo "✗ pg_dump упал. Контейнер postgres поднят? (docker compose ps)" >&2
  rm -f "$OUT"
  exit 1
fi

# 3. Проверить, что архив непустой и целый — иначе это не бэкап.
if [ ! -s "$OUT" ] || ! gzip -t "$OUT" 2>/dev/null; then
  echo "✗ Дамп пустой или битый — удаляю ${OUT}." >&2
  rm -f "$OUT"
  exit 1
fi

# 4. Ротация: удалить дампы старше KEEP_DAYS суток.
find "$BACKUP_DIR" -maxdepth 1 -name "${DB_NAME}-*.sql.gz" -type f -mtime +"${KEEP_DAYS}" -delete

SIZE="$(du -h "$OUT" | cut -f1)"
COUNT="$(find "$BACKUP_DIR" -maxdepth 1 -name "${DB_NAME}-*.sql.gz" -type f | wc -l | tr -d ' ')"
echo "✓ Готово: ${OUT} (${SIZE}). Всего копий: ${COUNT}, храним ${KEEP_DAYS} сут."
