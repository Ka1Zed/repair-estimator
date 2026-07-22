# Архитектура: контракт стора

Этот документ фиксирует точку стыка **Frontend 1** (редактор помещений) ↔ **Frontend 2** (смета).
Источник правды — `frontend/src/store/projectStore.ts`.

## Структура Zustand-стора

```ts
ProjectState {
  city:            string          // город для расчёта цен
  scope:           EstimateScope   // "finish_only" | "rough_and_finish" | "rough_only"
  store:           string | null   // выбранный магазин материалов; null — «Любой» (автоподбор)
  rooms:           Room[]
  activeRoomIndex: number
}
```

`scope` определяет объём сметы (только чистовая / черновая+чистовая / только черновая) и
уходит в `POST /api/estimates/calculate` как есть. `store` (#365) ограничивает подбор цен
материалов одним магазином (Мегастрой / Леман) — в запрос уходит как массив `stores` (`null`
или `[store]`). Старые поля `repair_type`/`repair_options` из ранних версий стора удалены —
их заменил `scope` на уровне проекта плюс `works` на уровне каждой комнаты (см. ниже).

## Тип Room

Поля, которые Frontend 1 кладёт в стор и которые Frontend 2 читает для отправки в API:

| Поле        | Тип                            | Описание                                          |
|-------------|--------------------------------|---------------------------------------------------|
| `id`        | `string` (UUID)                | Локальный идентификатор, в API не отправляется    |
| `name`      | `string`                       | Название комнаты («Комната», «Влажное помещение») |
| `height`    | `number \| string`             | Высота потолка в метрах; конвертировать через `Number()` перед отправкой |
| `room_type` | `"living" \| "kitchen" \| "bathroom" \| "hallway"` | Тип комнаты — пресет дефолтов отделки. Пользователь его **не выбирает явно** (#366); «влажность» задаётся чекбоксом «Влажное помещение» в `WorksPanel` |
| `points`    | `{ x: number \| string, y: number \| string }[]` | Вершины многоугольника в метрах; конвертировать через `Number()` перед отправкой |
| `openings`  | `Opening[]`                    | Проёмы (двери и окна)                             |
| `works`     | `RoomWorks`                    | Состав работ и отделка — на уровне комнаты        |
| `ceilingShape` | `CeilingShape`              | Форма потолка (#357); влияет на `ceiling_area` на бэкенде. В API уходит как `ceiling_shape` |

## Тип Opening

| Поле     | Тип                    | Описание                                              |
|----------|------------------------|-------------------------------------------------------|
| `id`     | `string` (UUID)        | Локальный идентификатор, в API не отправляется        |
| `type`   | `"door" \| "window"`   | Тип проёма                                            |
| `width`  | `number \| string`     | Ширина в метрах; конвертировать через `Number()` перед отправкой |
| `height` | `number \| string`     | Высота в метрах; конвертировать через `Number()` перед отправкой |

## Тип CeilingShape

Форма потолка на уровне комнаты (#357). Меняет только `ceiling_area` на бэкенде
(`geometry_service`), не `works.ceiling` (отделку). В API уходит как `ceiling_shape`.

| Поле           | Тип               | Описание                                                     |
|----------------|-------------------|--------------------------------------------------------------|
| `type`         | `"flat" \| "multilevel" \| "attic_slope"` | «Плоский» (`ceiling_area = floor_area`) / «Многоуровневый» / «Мансардный скат» |
| `levels`       | `number \| null`  | `multilevel`: число уровней короба (1–5)                     |
| `step_height_m`| `number \| null`  | `multilevel`: высота грани короба на уровень, м              |
| `slope_deg`    | `number \| null`  | `attic_slope`: угол ската от горизонтали, ° (0–85)           |

Дефолт — `{ type: "flat", levels: null, step_height_m: null, slope_deg: null }`.

## Тип RoomWorks

`works` — объект на каждую комнату. Управляется компонентом `WorksPanel`.
`allowedWorks(room_type)` из `roomTypes.ts` даёт список finish-вариантов из `finishOptions` для
подстановки в UI — это **не жёсткое ограничение** (бэкенд не отвергает нетипичные комбинации),
а только пресет дефолтов под тип комнаты.

### Отделочные группы

| Ключ       | Поле `enabled` | Поле `finish`                                       | Модификаторы                                      |
|------------|----------------|-------------------------------------------------------|---------------------------------------------------|
| `floor`    | `boolean`      | `"laminate" \| "linoleum" \| "parquet" \| "tile" \| null` | —                                          |
| `walls`    | `boolean`      | `"paint" \| "wallpaper" \| "tile" \| "moisture_paint" \| null` | `wall_condition: "even" \| "normal" \| "uneven"`, `wallpaper_pattern: boolean`, `primer_two_coats: boolean` |
| `ceiling`  | `boolean`      | `"paint" \| "moisture_paint" \| "stretch" \| null`  | `primer_two_coats: boolean`                       |

`wall_condition` масштабирует расход стартовой шпаклёвки (кривизна стен) — добавлено в версии 4 стора.

### Инженерные группы

| Ключ        | Поле `enabled` | Числовые поля                                        |
|-------------|----------------|--------------------------------------------------------|
| `electric`  | `boolean`      | `sockets: number \| null`, `lights: number \| null`, `cable_m: number \| null` |
| `plumbing`  | `boolean`      | `points: number \| null`, `pipe_m: number \| null`   |

Сантехника (`plumbing`) отображается в `WorksPanel` только если `allowedWorks(room_type).plumbing.available === true`.

## Сборка payload для POST /api/estimates/calculate

`Workspace.tsx` строит тело запроса так:

```ts
{
  city,                    // из стора
  scope,                   // из стора
  tier: "avg",              // фиксированный запрос; ответ содержит min/avg/max по каждой позиции
  stores: store ? [store] : null,  // из стора: ограничить подбор цен магазином (или «Любой»)
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
    works: room.works,     // состав работ на уровне комнаты
    ceiling_shape: {       // форма потолка (#357)
      type: room.ceilingShape.type,
      levels: room.ceilingShape.levels,
      step_height_m: room.ceilingShape.step_height_m,
      slope_deg: room.ceilingShape.slope_deg,
    },
  })),
}
```

Сборку тела выполняет `utils/roomsToPayload.ts` (`roomsToCalcPayload`), числовые поля
конвертируются через `Number()`. Полный контракт запроса/ответа — в `docs/api.md`.

Поля `id` из `Room` и `Opening` в запрос не включаются — они только локальные.

## Действия стора (кратко)

Помимо сеттеров полей комнаты/проёмов (`setCity`, `setScope`, `setHeight`, `updatePoint`,
`setPoints`, `addOpening`/`updateOpening`/`deleteOpening`, `updateRoomWorks` и т.д.) стор даёт:

- `loadProject(project)` — заполняет стор данными сохранённого проекта (`city`, `scope`, `rooms`);
  используется страницей «Мои проекты» при открытии. Имя проекта (`name`) в стор **не попадает** —
  оно прокидывается отдельно через `Page`-роутинг (`App.tsx` → `Workspace` проп `projectName`).
- `resetProject()` — сброс к дефолтному состоянию (одна пустая комната).
- `clearActiveRoom()` — очищает точки и проёмы активной комнаты, не трогая остальные поля.
- `loadDemoRoom()` — подставляет демо-геометрию в активную комнату (используется кнопкой
  «Загрузить пример» и демо-распознаванием чертежа).

## Инварианты (не нарушать)

- `height`, `x`, `y`, `width`, `height` в проёмах хранятся как `number | string` (пользователь может ввести строку в input). Перед отправкой в API всегда конвертировать через `Number()`.
- `works` — один объект на комнату. Разные комнаты могут иметь разные наборы работ.
- `works.floor.finish` (и аналогично walls/ceiling) валидируется на фронте по `allowedWorks(room_type)`, но бэкенд не отвергает нетипичные комбинации.
- `activeRoomIndex` — только UI-состояние, в API не отправляется.
- Имя проекта (`ProjectSummary.name`/`Project.name`) не хранится в сторе — это отдельное локальное
  состояние `Workspace` (`projectName`), синхронизируемое через проп при открытии сохранённого
  проекта. Не путать со стором при доработке контракта.
- Версия стора: **5**. Миграция v1→v2 переносит `repair_options` с уровня комнат на уровень проекта; v2→v3 добавляет `works` в каждую комнату по умолчанию из `defaultWorksForRoomType(room_type)`; v3→v4 добавляет `walls.wall_condition` (дефолт `"normal"` для старых записей); v4→v5 добавляет `ceilingShape` (дефолт `DEFAULT_CEILING_SHAPE` — плоский потолок) для старых записей.
