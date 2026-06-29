# Обновление цен (раннбук)

Как обновить цены в проде, проверить их и что делать, если сломалось.

## Как устроено (коротко)

- Расчёт сметы **не ходит в сеть**: в проде `PARSER_LIVE_FETCH=false`, сервер читает
  цены только из БД. Живой парсинг — у CLI `python -m app.manage update_prices`.
- Цены «живут» `PRICE_TTL_HOURS` (по умолчанию 24 ч). Строка старше TTL игнорируется —
  расчёт уходит на seed-fallback. Никакого кэша в памяти процесса нет: смета читает БД
  свежей сессией на каждый запрос, поэтому после записи цен **рестарт не нужен**.
- Любой сбой парсера → seed. Смета никогда не падает из-за внешнего сайта.

Прод-БД доступна только через SSH-туннель (порт `5433` → `localhost:5432` на сервере).
Парсеры запускаются **локально с российского IP** (датацентр/прод режут РФ-сайты), а
пишут в прод-БД через туннель.

## Особый случай — Мегастрой за JS-проверкой

`kazan.megastroy.com` закрыт JS-challenge WAF (DDoS-Guard): голый `requests` ловит
мгновенный 403. IP при этом не забанен — браузер заходит после ~3-сек проверки.
Обход без headless — **cookie hand-off**: пройти проверку в браузере и отдать парсеру
свою cookie + User-Agent через env `MEGASTROY_COOKIE` / `MEGASTROY_UA`
(см. `app/parsers/megastroy_parser.py`). Cookie живёт недолго и привязана к IP+UA.

## 1. Обновить цены

VPN **выключен**. Cookie берём свежую прямо перед запуском.

```bash
# а) В браузере открыть страницу и пройти 3-сек проверку:
#    https://kazan.megastroy.com/catalog/kraski-dlya-vnutrennih-rabot
#    DevTools (Cmd+Option+I) → вкладка Network → Cmd+R → клик по запросу документа
#    → Request Headers → скопировать строки Cookie и User-Agent.

cd ~/SummerProject/repair-estimator/backend
source .venv/bin/activate

# б) Вставить свежие значения из браузера:
export MEGASTROY_UA='<строка User-Agent>'
export MEGASTROY_COOKIE='<строка Cookie>'

# в) Поднять туннель к прод-БД:
pkill -f "5433:localhost:5432" 2>/dev/null
ssh -i ~/.ssh/repair_deploy_ed25519 -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 \
    -f -N -L 5433:localhost:5432 zharenovkostya@35.254.13.119

# г) Записать цены в прод-БД (пароль — из ~/refresh-prices.sh):
POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5433 POSTGRES_DB=repair_estimator \
POSTGRES_USER=repair POSTGRES_PASSWORD='<пароль>' \
  python -m app.manage update_prices
```

В логах ждём `✓ Краска для стен: avg=...` (а не `403 → seed`) и в конце `Готово. Успешно: N`.

## 2. Проверить, что прод отдаёт свежее

Туннель поднят. Материалы (Мегастрой):

```bash
PGPASSWORD='<пароль>' psql -h 127.0.0.1 -p 5433 -U repair -d repair_estimator -c "
select m.name, p.price_avg, s.name as source,
       round(extract(epoch from (now() - p.updated_at))/3600, 1) as age_h
from material_prices p
join materials m       on m.id = p.material_id
join price_sources s   on s.id = p.source_id
where s.name <> 'seed'
order by p.updated_at desc;"
```

Работы (региональные прайсы):

```bash
PGPASSWORD='<пароль>' psql -h 127.0.0.1 -p 5433 -U repair -d repair_estimator -c "
select ls.name, p.price_avg, s.name as source, p.region,
       round(extract(epoch from (now() - p.updated_at))/3600, 1) as age_h
from labor_prices p
join labor_services ls on ls.id = p.labor_service_id
join price_sources s   on s.id = p.source_id
where s.name <> 'seed'
order by p.updated_at desc;"
```

Хорошо = `source` не `seed` и `age_h` < 24. Без psql: дёрнуть прод `/estimate` и
проверить, что в строках `source` = имя парсера, а не `seed`.

## 3. Если сломалось

| Симптом | Причина | Что делать |
|---|---|---|
| `403 Forbidden` в логах | cookie протухла / UA не совпал | Обновить страницу → заново скопировать **Cookie и User-Agent из одного запроса** → повторить `export` и шаг «г» |
| `403` сразу даже со свежей cookie | VPN включён (IP не совпал с `__ddg9_`) | Выключить VPN, взять cookie заново |
| `connection refused` на 5433 | туннель отвалился | Повторить шаг «в»; проверить `lsof -iTCP:5433 -sTCP:LISTEN` |
| `age_h > 24` при показе | прошли сутки | Норма — повторить раздел 1 |
| В смете краска = seed (450/400) | Мегастрой не записался | Смотреть лог: была ли `✓` по краскам; если `403` — см. строку 1 |

**Инвариант:** пустые `MEGASTROY_COOKIE`/`MEGASTROY_UA` или любой сбой → seed-fallback,
смета считается дальше. Цены — улучшение, а не критичный путь.

## На будущее

Долгосрочный обход challenge без ручной cookie — headless-браузер (Playwright),
оформлен отдельным beta-планом. Качество вилки цен Мегастроя (берётся вся категория) —
issue #207.
