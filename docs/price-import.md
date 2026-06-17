# Импорт цен из CSV

Ручное обновление цен без парсинга сайтов. Импортированные цены сохраняются
с источником `manual` и свежей датой обновления.

## Формат CSV

Файл с заголовком, разделитель — запятая, кодировка UTF-8:

kind,name,price_min,price_avg,price_max

material,Краска для стен,320,480,650

labor,Покраска стен,210,260,360

| Колонка | Значение |
|---------|----------|
| `kind` | `material` (материал) или `labor` (услуга) |
| `name` | точное название позиции, как в БД |
| `price_min` | минимальная цена |
| `price_avg` | средняя цена |
| `price_max` | максимальная цена |

## Запуск

```python
from app.services.price_import_service import import_prices_from_file
result = import_prices_from_file("prices_sample.csv")
print(result)  # {"updated": N, "skipped": [...]}
```

## Поведение

- Если позиция с `source=manual` уже есть — цена обновляется, иначе создаётся.
- Строки с неизвестным `name` или некорректными ценами пропускаются
  (попадают в `skipped`), но не прерывают импорт остальных.