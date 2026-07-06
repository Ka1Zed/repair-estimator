#!/usr/bin/env bash
#
# deploy.sh — выкатка актуальной версии на сервер.
#
# Запускать НА сервере из корня репозитория:
#   ./deploy.sh           # выкатить ветку main (по умолчанию)
#   ./deploy.sh dev        # выкатить другую ветку
#
# Делает по шагам: подтягивает нужную ветку → пересобирает контейнеры → ждёт health.
# Данные БД (volume) и .env не трогаются. Seed идёт только при пустой БД (--if-empty).

set -euo pipefail

BRANCH="${1:-main}"
HEALTH_URL="${HEALTH_URL:-http://localhost:8000/health}"

# 0. Запуск из корня репозитория (рядом должен лежать docker-compose.yml).
if [ ! -f docker-compose.yml ]; then
  echo "✗ docker-compose.yml не найден. Запускай скрипт из корня репозитория." >&2
  exit 1
fi

# 1. .env обязателен — там адреса сервера и пароль БД, в git его нет.
if [ ! -f .env ]; then
  echo "✗ .env не найден. Скопируй .env.example → .env и пропиши FRONTEND_URL/VITE_API_URL/пароль БД." >&2
  exit 1
fi
for var in FRONTEND_URL VITE_API_URL; do
  if ! grep -q "^${var}=" .env; then
    echo "⚠ В .env нет ${var} — фронт/CORS может смотреть в localhost." >&2
  fi
done

# 2. Предупредить, если нет swap: на 1ГБ RAM пересборка фронта может упасть с OOM.
if [ "$(free -m 2>/dev/null | awk '/^Swap:/ {print $2}')" = "0" ]; then
  echo "⚠ Swap не настроен. На 1ГБ RAM пересборка может упасть с OOM (рекомендуется ~2ГБ swap)." >&2
fi

# 3. Не затереть случайные локальные правки трекаемых файлов (.env в .gitignore — не в счёт).
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "✗ Есть незакоммиченные изменения трекаемых файлов:" >&2
  git status --short --untracked-files=no >&2
  echo "  Разберись (git stash / git checkout -- <файл>) и запусти снова." >&2
  exit 1
fi

# 4. Подтянуть актуальную версию ветки (только fast-forward — без случайных merge-коммитов).
echo "→ Обновляю ветку '${BRANCH}'…"
git fetch origin --tags --prune
git checkout "${BRANCH}"
git pull --ff-only origin "${BRANCH}"
echo "  Текущий коммит: $(git log -1 --oneline)"

# 5. Пересборка и запуск. --build обязателен: VITE_API_URL зашивается в бандл фронта.
#    --remove-orphans убирает контейнеры от прежних топологий (напр. старый caddy,
#    державший 80/443 после отката), иначе новый стек не займёт порты.
echo "→ Пересобираю и поднимаю контейнеры…"
docker compose up -d --build --remove-orphans

# 6. Дождаться зелёного health backend.
echo "→ Жду health backend (${HEALTH_URL})…"
for _ in $(seq 1 30); do
  if curl -fsS "${HEALTH_URL}" >/dev/null 2>&1; then
    echo "✓ Готово: $(curl -fsS "${HEALTH_URL}")"
    docker compose ps
    exit 0
  fi
  sleep 2
done

echo "✗ health не ответил за 60с. Логи: docker compose logs -f backend" >&2
docker compose ps >&2
exit 1
