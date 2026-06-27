# Архитектура: контракт стора

Этот документ фиксирует точку стыка **Frontend 1** (редактор помещений) ↔ **Frontend 2** (смета).
Источник правды — `frontend/src/store/projectStore.ts`.

## Структура Zustand-стора

```ts
ProjectState {
  repair_type:    "cosmetic" | "base" | "extended"
  repair_options: RepairOptions          // опции работ, общие для всего проекта
  rooms:          Room[]
  activeRoomIndex: number
}
```

## Тип Room

Поля, которые Frontend 1 кладёт в стор и которые Frontend 2 читает для отправки в API:

| Поле        | Тип                            | Описание                                          |
|-------------|--------------------------------|---------------------------------------------------|
| `id`        | `string` (UUID)                | Локальный идентификатор, в API не отправляется    |
| `name`      | `string`                       | Название комнаты («Спальня», «Кухня»)             |
| `height`    | `number \| string`             | Высота потолка в метрах; конвертировать через `Number()` перед отправкой |
| `room_type` | `"living" \| "kitchen" \| "bathroom" \| "hallway"` | Тип комнаты                   |
| `points`    | `{ x: number \| string, y: number \| string }[]` | Вершины многоугольника в метрах; конвертировать через `Number()` перед отправкой |
| `openings`  | `Opening[]`                    | Проёмы (двери и окна)                             |

## Тип Opening

| Поле     | Тип                    | Описание                                              |
|----------|------------------------|-------------------------------------------------------|
| `id`     | `string` (UUID)        | Локальный идентификатор, в API не отправляется        |
| `type`   | `"door" \| "window"`   | Тип проёма                                            |
| `width`  | `number \| string`     | Ширина в метрах; конвертировать через `Number()` перед отправкой |
| `height` | `number \| string`     | Высота в метрах; конвертировать через `Number()` перед отправкой |

## Тип RepairOptions (уровень проекта)

`repair_options` — единый объект для всего проекта, не привязан к отдельной комнате.
Управляется компонентом `WorksCheckboxes` и применяется ко всем комнатам при расчёте.

| Поле       | Тип                  | Значения                                           |
|------------|----------------------|----------------------------------------------------|
| `floor`    | `string \| null`     | `"laminate"`, `"linoleum"`, `"parquet"`, `"tile"`, `null` |
| `walls`    | `string \| null`     | `"paint"`, `"wallpaper"`, `"tile"`, `null`         |
| `ceiling`  | `string \| null`     | `"paint"`, `"stretch"`, `null`                     |
| `electric` | `string \| null`     | `"basic"`, `"extended"`, `null`                    |
| `plumbing` | `boolean`            | Сантехника                                         |

Допустимые значения per room_type — см. `docs/room-types.json`.

## Сборка payload для POST /api/estimates/calculate

Frontend 2 (`EstimateResult.tsx`) строит тело запроса так:

```ts
{
  city: "Казань",                  // TODO: вынести в стор
  repair_type,                     // из стора
  repair_options,                  // из стора (проектный уровень)
  rooms: rooms.map(room => ({
    name: room.name,
    room_type: room.room_type,
    height: Number(room.height),
    points: room.points.map(p => ({ x: Number(p.x), y: Number(p.y) })),
    openings: room.openings.map(op => ({
      type: op.type,
      width: Number(op.width),
      height: Number(op.height),
    })),
  })),
}
```

Поля `id` из `Room` и `Opening` в запрос не включаются — они только локальные.

## Инварианты (не нарушать)

- `height`, `x`, `y`, `width`, `height` в проёмах хранятся как `number | string` (пользователь может ввести строку в input). Перед отправкой в API всегда конвертировать через `Number()`.
- `repair_options` — один на проект. Если комнатам нужны разные опции, это потребует изменения API-контракта (задача за рамками MVP).
- `activeRoomIndex` — только UI-состояние, в API не отправляется.
