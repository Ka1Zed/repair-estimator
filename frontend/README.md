# Frontend

## Локальный запуск

```bash
cd frontend
npm install
npm run dev
```

Приложение откроется на `http://localhost:5173`. Vite-прокси перенаправляет
`/api/*` и `/health` на `http://localhost:8000` (бэкенд по умолчанию).

## Адрес бэкенда

По умолчанию фронт использует **относительные пути** (`/api/…`, `/health`).
В dev это обрабатывает Vite-прокси, в production — nginx (см. `nginx.conf`).

Если бэкенд находится на другом хосте (cross-origin деплой), создайте
`frontend/.env.local`:

```
VITE_API_URL=https://api.example.com
```

Переменная встраивается в бандл при `npm run build` — убедитесь, что она
задана до сборки.

## Сборка

```bash
npm run build   # результат в dist/
```
