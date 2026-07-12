import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import styles from "./Workspace.module.css";

import RoomsList from "../../components/RoomsList";
import RoomPolygonEditor from "../../components/RoomPolygonEditor";
import RoomPointsTable from "../../components/RoomPointsTable";
import BlueprintUpload from "../../components/BlueprintUpload";
import OpeningsForm from "../../components/OpeningsForm";
import { RoomTypeSelector } from "../../components/RoomTypeSelector";
import { WorksPanel } from "../../components/WorksPanel/WorksPanel";

import type { MaterialItem, PriceVariant, LaborItem, LaborStage, HiddenWorks } from "../../types/estimate";
import type { SummaryData } from "../../components/EstimateSummary";
import { EstimateLedger, type LedgerRow, type LedgerRowVariant } from "../../components/EstimateLedger/EstimateLedger";
import { useProjectStore, type EstimateScope } from "../../store/projectStore";
import { useBackendStatus } from "../../store/backendStatus";
import { roomHasInvalidOpenings } from "../../utils/openingValidation";
import { hasSelfIntersection, validateHeight } from "../../utils/polygonValidation";
import { calculateEstimate } from "../../api/estimates";
import { apiClient } from "../../api/client";
import { Select } from "../../components/ui/Select";

interface GeometryData {
  floor_area: number;
  ceiling_area: number;
  wall_area: number;
  perimeter: number;
}

interface EstimateResponse {
  summary: SummaryData;
  geometry: GeometryData;
  materials: MaterialItem[];
  labor: LaborItem[];
  scope?: EstimateScope;
  hidden_works?: HiddenWorks;
}

const STAGE_LABELS: Record<LaborStage, string> = {
  rough: "Черновые работы",
  pre_finish: "Предчистовые работы",
  finish: "Чистовые работы",
};

const formatPrice = (price: number) => `${Math.round(price).toLocaleString("ru-RU")} ₽`;
const formatNum = (n: number) =>
  n.toLocaleString("ru-RU", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const formatQty = (n: number) => n.toLocaleString("ru-RU", { maximumFractionDigits: 1 });
const rub = (n: number) => `${n.toLocaleString("ru-RU")} ₽`;

// Регион, по которому реально взялась цена; null → нерегиональный источник
// (парсер отдаёт один и тот же каталог на все города, см. docs/price-sources.md).
// Мегастрой и базовый Леман физически используют домен kazan.* при ЛЮБОМ выбранном
// городе (проверено вживую: тот же source_url для Москвы/Новосибирска/Казани) —
// подставлять "Казань" им всегда было бы неправдой. Честно можно показать город
// только когда пользователь и правда выбрал Казань — тогда это совпадает с фактом.
const regionLabel = (
  region: string | null | undefined,
  sourceUrl: string | null | undefined,
  selectedCity: string,
) => {
  if (region) return region;
  if (selectedCity === "Казань" && sourceUrl?.includes("kazan.")) return "Казань";
  return "базовая цена";
};

// "company_price" — источник rembrigada116.ru (казанская компания), но так
// исторически называется в БД (см. rembrigada_parser.py) — не показываем сырой
// внутренний код клиенту.
const LABOR_SOURCE_NAMES: Record<string, string> = { company_price: "rembrigada116.ru" };
const laborSourceName = (source: string) => LABOR_SOURCE_NAMES[source] ?? source;

// Резерв на непредвиденные (CONTINGENCY, backend/app/services/repair_coeffs_service.py),
// уже включён в "Итог по позиции" — поэтому итог не равен цене за единицу × кол-во.
const CONTINGENCY_PCT: Record<PriceMode, number> = { min: 10, avg: 12, max: 15 };

export type PriceMode = "min" | "avg" | "max";

export function Workspace() {
  const rooms = useProjectStore((s) => s.rooms);
  const city = useProjectStore((s) => s.city);
  const setCity = useProjectStore((s) => s.setCity);
  const scope = useProjectStore((s) => s.scope);
  const setScope = useProjectStore((s) => s.setScope);
  const activeRoomIndex = useProjectStore((s) => s.activeRoomIndex);
  const activeRoom = rooms[activeRoomIndex];
  const setHeight = useProjectStore((s) => s.setHeight);

  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<EstimateResponse | null>(null);
  const [tab, setTab] = useState<"materials" | "labor">("materials");
  const [regions, setRegions] = useState<string[]>([]);

  // resizable split
  const containerRef = useRef<HTMLDivElement>(null);
  const dividerDragging = useRef(false);
  const [splitPct, setSplitPct] = useState(55);
  const [isDividerDragging, setIsDividerDragging] = useState(false);

  // interactive range state
  const trackRef = useRef<HTMLDivElement>(null);
  const [priceMode, setPriceMode] = useState<PriceMode>("avg");
  const [isDragging, setIsDragging] = useState(false);
  const [dragPos, setDragPos] = useState(0);

  // Точечное переопределение уровня для конкретного материала (индекс в data.materials)
  // поверх глобального ползунка: выбрали "Минимум" глобально, но зажали конкретный
  // товар на "Премиум" — держится, пока не пересчитаем смету или не кликнут ещё раз.
  const [materialOverrides, setMaterialOverrides] = useState<Record<number, PriceMode>>({});
  const toggleMaterialOverride = useCallback((index: number, mode: PriceMode) => {
    setMaterialOverrides((prev) => {
      if (prev[index] === mode) {
        const next = { ...prev };
        delete next[index];
        return next;
      }
      return { ...prev, [index]: mode };
    });
  }, []);

  // То же самое для работ (индекс в data.labor): у работ нет альтернативного
  // исполнителя по tier, только цена внутри коридора price_min/avg/max строки.
  const [laborOverrides, setLaborOverrides] = useState<Record<number, PriceMode>>({});
  const toggleLaborOverride = useCallback((index: number, mode: PriceMode) => {
    setLaborOverrides((prev) => {
      if (prev[index] === mode) {
        const next = { ...prev };
        delete next[index];
        return next;
      }
      return { ...prev, [index]: mode };
    });
  }, []);

  // Список городов для селектора. Если текущего города нет в ответе бэка,
  // всё равно показываем его — расчёт по нему уйдёт в seed-fallback.
  useEffect(() => {
    apiClient
      .fetchRegions()
      .then((res) => setRegions(res.regions))
      .catch((err) => {
        console.error("Не удалось загрузить список городов:", err);
        // fetchRegions падает первым при мёртвом бэке — поднимаем баннер.
        useBackendStatus.getState().setBackendDown(true);
      });
  }, []);

  const cityOptions = useMemo(
    () => (regions.includes(city) ? regions : [city, ...regions]),
    [regions, city],
  );

  // silent=true — авто-пересчёт по дебаунсу: молча пропускаем невалидное состояние,
  // не пугаем пользователя ошибкой, пока он редактирует.
  const runCalculate = useCallback(
    async (silent: boolean) => {
      const geometryValid = rooms.every(
        (r) => r.points.length >= 3 && r.height !== "" && Number(r.height) > 0,
      );
      if (!geometryValid) {
        if (!silent) {
          setError("У каждой комнаты нужны минимум 3 точки и высота потолка больше нуля.");
        }
        return;
      }

      // Невалидные проёмы не отправляем: иначе кривая ширина/высота уедет в wall_area.
      if (rooms.some(roomHasInvalidOpenings)) {
        if (!silent) {
          setError(
            "Проверьте размеры проёмов: ширина и высота должны быть больше нуля и не превышать допустимых пределов.",
          );
        }
        return;
      }

      if (rooms.some((r) => r.points.length >= 3 && hasSelfIntersection(r.points))) {
        if (!silent) {
          setError("Контур комнаты самопересекается — площадь будет неверной. Исправьте форму.");
        }
        return;
      }

      // validateHeight ловит и верхний предел (> 10 м), который geometryValid пропускает.
      if (rooms.some((r) => validateHeight(r.height) !== null)) {
        if (!silent) {
          setError("Высота потолка должна быть больше нуля и не превышать 10 м.");
        }
        return;
      }

      setIsLoading(true);
      setError(null);
      try {
        const payload = {
          city,
          scope,
          rooms: rooms.map((room) => ({
            name: room.name,
            room_type: room.room_type,
            height: Number(room.height),
            openings: room.openings.map((op) => ({
              ...op,
              width: Number(op.width),
              height: Number(op.height),
            })),
            points: room.points.map((p) => ({ x: Number(p.x), y: Number(p.y) })),
            works: room.works,
          })),
        };
        // Запрашиваем все три tier параллельно (#331): для 6 finish_key-позиций
        // (ламинат, покраска стен/потолка, плитка, обои, розетка) tier меняет
        // конкретный товар (name/source_url), не только цену. Геометрия/работы
        // берутся из avg-ответа; материалы и «Вилка стоимости» материалов — из
        // реальных min/max-tier сумм (иначе сводка ±15-20% коридора расходится
        // с построчными итогами, которые теперь берут настоящие эконом/премиум SKU).
        const [minRes, avgRes, maxRes] = (await Promise.all([
          calculateEstimate({ ...payload, tier: "min" }),
          calculateEstimate({ ...payload, tier: "avg" }),
          calculateEstimate({ ...payload, tier: "max" }),
        ])) as [EstimateResponse, EstimateResponse, EstimateResponse];

        const toVariant = (m?: MaterialItem): PriceVariant | null =>
          m
            ? { name: m.name, price: m.price_avg, total: m.total_avg, source: m.source, source_url: m.source_url ?? null }
            : null;

        const sameLength =
          avgRes.materials.length === minRes.materials.length &&
          avgRes.materials.length === maxRes.materials.length;

        const materials = sameLength
          ? avgRes.materials.map((m, i) => ({
              ...m,
              min_item: toVariant(minRes.materials[i]),
              avg_item: toVariant(avgRes.materials[i]),
              max_item: toVariant(maxRes.materials[i]),
            }))
          : avgRes.materials;

        const summary = sameLength
          ? (() => {
              const materialsMin = minRes.materials.reduce((s, m) => s + (m.total_avg ?? 0), 0);
              const materialsMax = maxRes.materials.reduce((s, m) => s + (m.total_avg ?? 0), 0);
              return {
                ...avgRes.summary,
                materials_min: materialsMin,
                materials_max: materialsMax,
                total_min: materialsMin + avgRes.summary.labor_min,
                total_max: materialsMax + avgRes.summary.labor_max,
              };
            })()
          : avgRes.summary;

        setData({ ...avgRes, summary, materials });
        setPriceMode("avg");
        setMaterialOverrides({});
        setLaborOverrides({});
      } catch (err) {
        console.error(err);
        if (!silent) {
          setError("Не удалось рассчитать смету. Проверьте, что бэкенд запущен.");
        }
      } finally {
        setIsLoading(false);
      }
    },
    [rooms, city, scope],
  );

  // Авто-пересчёт через 500 мс после последнего изменения геометрии/параметров.
  // Дебаунс схлопывает всё перетаскивание угла в один запрос к бэку.
  useEffect(() => {
    const timer = setTimeout(() => runCalculate(true), 500);
    return () => clearTimeout(timer);
  }, [runCalculate]);

  const handleCalculate = () => runCalculate(false);

  const hasInvalidOpenings = useMemo(
    () => rooms.some(roomHasInvalidOpenings),
    [rooms],
  );

  const hasSelfIntersectingPolygon = useMemo(
    () => rooms.some((r) => r.points.length >= 3 && hasSelfIntersection(r.points)),
    [rooms],
  );

  const heightError = useMemo(
    () => validateHeight(activeRoom?.height ?? ""),
    [activeRoom?.height],
  );

  const hasInvalidHeight = useMemo(
    () => rooms.some((r) => validateHeight(r.height) !== null),
    [rooms],
  );

  // --- divider drag handlers ---
  const handleDividerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    dividerDragging.current = true;
    setIsDividerDragging(true);
  };

  const handleDividerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!dividerDragging.current || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    // вычитаем padding 24px с каждой стороны (.page), чтобы курсор не отставал
    const paddingX = 24;
    const contentWidth = rect.width - paddingX * 2;
    const pct = ((e.clientX - rect.left - paddingX) / contentWidth) * 100;
    setSplitPct(Math.min(75, Math.max(25, Math.round(pct))));
  };

  const handleDividerUp = () => {
    dividerDragging.current = false;
    setIsDividerDragging(false);
  };

  // Слайдер вилки: позиция средней между min и max
  const avgPos = useMemo(() => {
    if (!data) return 50;
    const { total_min, total_avg, total_max } = data.summary;
    if (total_max <= total_min) return 50;
    return ((total_avg - total_min) / (total_max - total_min)) * 100;
  }, [data]);

  // --- drag handlers ---
  const getPosFromEvent = (e: React.PointerEvent): number => {
    if (!trackRef.current) return 0;
    const rect = trackRef.current.getBoundingClientRect();
    return Math.max(0, Math.min(100, ((e.clientX - rect.left) / rect.width) * 100));
  };

  const snapToMode = (pos: number): PriceMode => {
    const dMin = Math.abs(pos);
    const dAvg = Math.abs(pos - avgPos);
    const dMax = Math.abs(pos - 100);
    if (dMin <= dAvg && dMin <= dMax) return "min";
    if (dMax <= dAvg) return "max";
    return "avg";
  };

  const handleTrackPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!data) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    const pos = getPosFromEvent(e);
    setIsDragging(true);
    setDragPos(pos);
  };

  const handleTrackPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!isDragging) return;
    setDragPos(getPosFromEvent(e));
  };

  const handleTrackPointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!isDragging) return;
    setIsDragging(false);
    setPriceMode(snapToMode(getPosFromEvent(e)));
  };

  const dotVisualPos = isDragging
    ? dragPos
    : priceMode === "min"
    ? 0
    : priceMode === "max"
    ? 100
    : avgPos;

  // --- price scaling ---
  // Множитель выбранного режима СВОЙ для каждого раздела: берётся из min/avg/max
  // именно этого раздела. У позиций нет своих min/max (в контракте только
  // total_avg), поэтому масштабируем средние. Общий total-коэффициент здесь не
  // годится — у материалов и работ разный разброс, и «Итого по разделу» разошлось
  // бы с вилкой в сводной таблице выше.
  const priceScale = useCallback(
    (category: "materials" | "labor") => {
      if (!data) return 1;
      const s = data.summary;
      const avg = category === "materials" ? s.materials_avg : s.labor_avg;
      if (avg === 0) return 1;
      const min = category === "materials" ? s.materials_min : s.labor_min;
      const max = category === "materials" ? s.materials_max : s.labor_max;
      if (priceMode === "min") return min / avg;
      if (priceMode === "max") return max / avg;
      return 1;
    },
    [data, priceMode],
  );

  // Материалы с учётом эффективного уровня по каждой строке (глобальный ползунок,
  // если для строки нет точечного переопределения). Источник правды для materialRows
  // и для суммы раздела — чтобы не считать total дважды по разной логике.
  const materialsActive = useMemo(() => {
    const scale = priceScale("materials");

    return (data?.materials ?? []).map((m, i) => {
      const effectiveMode = materialOverrides[i] ?? priceMode;

      const variants: LedgerRowVariant[] = [];
      if (m.min_item) variants.push({ mode: "min", title: "Эконом", name: m.min_item.name, price: rub(Math.round(m.min_item.price)), url: m.min_item.source_url, onClick: () => toggleMaterialOverride(i, "min") });
      if (m.avg_item) variants.push({ mode: "avg", title: "Стандарт", name: m.avg_item.name, price: rub(Math.round(m.avg_item.price)), url: m.avg_item.source_url, onClick: () => toggleMaterialOverride(i, "avg") });
      if (m.max_item) variants.push({ mode: "max", title: "Премиум", name: m.max_item.name, price: rub(Math.round(m.max_item.price)), url: m.max_item.source_url, onClick: () => toggleMaterialOverride(i, "max") });

      const activeVariant = effectiveMode === "min" ? m.min_item : effectiveMode === "max" ? m.max_item : m.avg_item;
      const activeName = activeVariant?.name ?? m.name;
      const activePrice = activeVariant ? activeVariant.price : m.price_avg * scale;
      const activeTotal = activeVariant ? activeVariant.total : m.total_avg * scale;
      const activeUrl = activeVariant?.source_url ?? m.source_url;
      const activeSource = activeVariant?.source ?? m.source;

      // Ссылка на товар уже есть у каждой карточки в "Варианты материалов" —
      // здесь просто перечисляем источники без дублирования ссылки.
      const sourceNames = Array.from(
        new Set([m.min_item?.source, m.avg_item?.source, m.max_item?.source].filter((s): s is string => !!s)),
      );
      const sourceLabel = sourceNames.length > 0 ? sourceNames.join(", ") : activeSource;

      return { m, effectiveMode, activeName, activePrice, activeTotal, activeUrl, sourceLabel, sourceCount: sourceNames.length, variants };
    });
  }, [data, priceScale, priceMode, materialOverrides, toggleMaterialOverride]);

  const materialRows: LedgerRow[] = useMemo(
    () =>
      materialsActive.map(({ m, effectiveMode, activeName, activePrice, activeTotal, activeUrl, sourceLabel, sourceCount, variants }) => ({
        name: activeName,
        volume: `${formatQty(m.quantity)} ${m.unit}`,
        price: rub(Math.round(activePrice)),
        activeMode: effectiveMode,
        variants: variants.length > 0 ? variants : undefined,
        details: [
          { label: "Базовое кол-во", value: `${formatQty(m.base_quantity)} ${m.unit}` },
          { label: "Запас", value: `×${m.waste_factor} (+${Math.round((m.waste_factor - 1) * 100)}%)` },
          { label: "Упаковок", value: `${m.packs} × ${m.package_size} ${m.unit}` },
          { label: "Итого кол-во", value: `${formatQty(m.quantity)} ${m.unit}` },
          { label: "Цена за единицу", value: rub(Math.round(activePrice)) },
          {
            label: "Итог по позиции",
            value: `${rub(Math.round(activeTotal))} (с резервом +${CONTINGENCY_PCT[effectiveMode]}%)`,
          },
          {
            label: sourceCount > 1 ? "Источники цены" : "Источник цены",
            value: sourceLabel,
            ...(variants.length > 0 ? {} : { url: activeUrl }),
          },
          { label: "Регион", value: regionLabel(m.region, activeUrl, city) },
          ...(m.updated_at
            ? [{ label: "Обновлено", value: new Date(m.updated_at).toLocaleDateString("ru-RU") }]
            : []),
        ],
      })),
    [materialsActive, city],
  );

  // Работы с учётом эффективного уровня по каждой строке. В отличие от материалов,
  // у работы нет альтернативного исполнителя по tier — только цена внутри своего
  // коридора (price_min/avg/max), уже посчитанного бэкендом для строки.
  const laborActive = useMemo(() => {
    const scale = priceScale("labor");

    return (data?.labor ?? []).map((l, i) => {
      const effectiveMode = laborOverrides[i] ?? priceMode;
      const hasCorridor = l.price_min != null && l.price_max != null;

      const activePrice = !hasCorridor
        ? l.price_avg * scale
        : effectiveMode === "min"
          ? l.price_min!
          : effectiveMode === "max"
            ? l.price_max!
            : l.price_avg;
      const activeTotal = !hasCorridor
        ? l.total_avg * scale
        : effectiveMode === "min"
          ? (l.total_min ?? l.total_avg)
          : effectiveMode === "max"
            ? (l.total_max ?? l.total_avg)
            : l.total_avg;

      // Мин./макс. цена в коридоре — это реально цены разных компаний из l.sources
      // (посчитаны на бэкенде из нескольких прайс-листов), но бэкенд не сообщает,
      // ЧЬЯ именно цена дала каждую границу — только "представительный" source_url,
      // общий для всей строки (по документации — тот, чья средняя ближе к итоговой,
      // т.е. соответствует именно avg). Поэтому ссылку ставим только на «Стандарт»,
      // у «Эконом»/«Премиум» её быть не может — компания неизвестна; список всех
      // участников — одной строкой в "Источник(и) цены" ниже.
      const variants: LedgerRowVariant[] = hasCorridor
        ? [
            { mode: "min", title: "Эконом", name: l.service, price: rub(Math.round(l.price_min!)), onClick: () => toggleLaborOverride(i, "min") },
            { mode: "avg", title: "Стандарт", name: l.service, price: rub(Math.round(l.price_avg)), url: l.source_url, onClick: () => toggleLaborOverride(i, "avg") },
            { mode: "max", title: "Премиум", name: l.service, price: rub(Math.round(l.price_max!)), onClick: () => toggleLaborOverride(i, "max") },
          ]
        : [];

      const sourceCount = l.sources?.length ?? (l.source ? 1 : 0);
      const sourceLabel =
        l.sources && l.sources.length > 1
          ? l.sources.map(laborSourceName).join(", ")
          : laborSourceName(l.source);

      return { l, effectiveMode, activePrice, activeTotal, variants, sourceLabel, sourceCount };
    });
  }, [data, priceScale, priceMode, laborOverrides, toggleLaborOverride]);

  const laborItemToRow = useCallback(
    ({ l, effectiveMode, activePrice, activeTotal, variants, sourceLabel, sourceCount }: (typeof laborActive)[number]): LedgerRow => ({
      name: l.service,
      subtitle: l.specialist,
      volume: `${formatQty(l.volume)} ${l.unit}`,
      price: rub(Math.round(activePrice)),
      activeMode: effectiveMode,
      variants: variants.length > 0 ? variants : undefined,
      details: [
        { label: "Специалист", value: l.specialist },
        { label: "Цена за единицу", value: rub(Math.round(activePrice)) },
        {
          label: "Итог по позиции",
          value: `${rub(Math.round(activeTotal))} (с резервом +${CONTINGENCY_PCT[effectiveMode]}%)`,
        },
        {
          label: sourceCount > 1 ? "Источники цены" : "Источник цены",
          value: sourceLabel,
          ...(sourceCount > 1 ? {} : { url: l.source_url }),
        },
        { label: "Регион", value: regionLabel(l.region, l.source_url, city) },
      ],
    }),
    [city],
  );

  const laborRows: LedgerRow[] = useMemo(
    () => laborActive.map(laborItemToRow),
    [laborActive, laborItemToRow],
  );

  // Работы, сгруппированные по стадиям (черновая/предчистовая/чистовая) — для
  // сметы «Черновая + чистовая». В режиме «только чистовая» группировки нет.
  const laborByStage = useMemo(() => {
    const groups = new Map<LaborStage, typeof laborActive>();
    for (const item of laborActive) {
      const stage: LaborStage = item.l.stage ?? "finish";
      if (!groups.has(stage)) groups.set(stage, []);
      groups.get(stage)!.push(item);
    }
    return groups;
  }, [laborActive]);

  const sectionTotal = useMemo(() => {
    if (!data) return 0;
    const items = tab === "materials" ? materialsActive : laborActive;
    return Math.round(items.reduce((s, x) => s + x.activeTotal, 0));
  }, [data, tab, materialsActive, laborActive]);

  return (
    <div className={styles.page} ref={containerRef}>
      {/* ===== ЛЕВО: редактор ===== */}
      <section className={styles.left} style={{ width: `${splitPct}%` }}>
        <div className={styles.eyebrow}>Проект · план помещения</div>
        <h1 className={styles.title}>
          Постройте комнату
          <br />и выберите параметры
        </h1>
        <p className={styles.lead}>
          Тяните углы плана, кликайте по стене, чтобы добавить точку, по размеру — чтобы
          задать длину. Загрузите чертёж (beta) или стройте вручную. Аналитика справа
          обновляется по кнопке «Рассчитать».
        </p>

        <RoomsList />

        <div className={styles.block}>
          <RoomPolygonEditor />
        </div>

        <div className={styles.paramsRow}>
          <div className={styles.cityField}>
            <div className={styles.blockLabel}>Город (цены)</div>
            <Select
              variant="underline"
              ariaLabel="Город для расчёта цен"
              value={city}
              options={cityOptions.map((c) => ({ value: c, label: c }))}
              onChange={setCity}
            />
          </div>
          <div className={styles.heightField}>
            <div className={styles.blockLabel}>Высота потолка</div>
            <div>
              <input
                className={styles.heightInput}
                type="number"
                step="0.1"
                min="0.01"
                value={activeRoom?.height ?? ""}
                onChange={(e) => setHeight(e.target.value)}
              />
              <span className={styles.heightUnit}>м</span>
            </div>
            {heightError && (
              <div className={styles.error} style={{ marginTop: 4, fontSize: 12 }}>
                {heightError}
              </div>
            )}
          </div>
          <div>
            <div className={styles.blockLabel}>Объём ремонта</div>
            <div className={styles.scopeToggle}>
              <button
                className={`${styles.scopeBtn} ${scope === "finish_only" ? styles.scopeBtnActive : ""}`}
                onClick={() => setScope("finish_only")}
              >
                Только чистовая
              </button>
              <button
                className={`${styles.scopeBtn} ${scope === "rough_and_finish" ? styles.scopeBtnActive : ""}`}
                onClick={() => setScope("rough_and_finish")}
              >
                Черновая + чистовая
              </button>
            </div>
          </div>
        </div>

        <div className={styles.block}>
          <div className={styles.blockLabel}>Тип комнаты</div>
          <RoomTypeSelector />
        </div>

        <div className={styles.block}>
          <div className={styles.blockLabel}>Состав работ</div>
          <WorksPanel />
        </div>

        <div className={styles.block}>
          <OpeningsForm />
        </div>

        <details className={styles.pointsDetails}>
          <summary className={styles.pointsSummary}>Координаты углов</summary>
          <div className={styles.pointsBody}>
            <RoomPointsTable />
          </div>
        </details>

        <div className={styles.block}>
          <BlueprintUpload />
        </div>

        {data && (
          <div className={styles.planTotal}>
            <span className={styles.planTotalLabel}>Ориентировочно</span>
            <span className={styles.planTotalValue}>{formatPrice(data.summary.total_avg)}</span>
          </div>
        )}

        <button
          className={styles.calcBtn}
          onClick={handleCalculate}
          disabled={
            isLoading ||
            hasInvalidOpenings ||
            hasSelfIntersectingPolygon ||
            hasInvalidHeight
          }
        >
          {isLoading ? "Считаем…" : "Рассчитать смету"}
        </button>
        {hasInvalidOpenings && (
          <div className={styles.error}>
            Исправьте размеры проёмов — расчёт недоступен.
          </div>
        )}
        {hasSelfIntersectingPolygon && (
          <div className={styles.error}>
            Контур комнаты самопересекается — исправьте форму.
          </div>
        )}
        {error && <div className={styles.error}>{error}</div>}
      </section>

      {/* ===== РАЗДЕЛИТЕЛЬ (перетаскивается) ===== */}
      <div
        className={`${styles.divider} ${isDividerDragging ? styles.dividerDragging : ""}`}
        onPointerDown={handleDividerDown}
        onPointerMove={handleDividerMove}
        onPointerUp={handleDividerUp}
        onPointerCancel={handleDividerUp}
      />

      {/* ===== ПРАВО: аналитика ===== */}
      <aside className={styles.right}>
        <div className={styles.rightSticky}>
          <div className={styles.rightHeader}>
            <div>
              <div className={styles.eyebrow}>Смета · предв. расчёт</div>
              <div className={styles.rightHeaderSub}>
                {rooms.length}{" "}
                {rooms.length === 1 ? "комната" : rooms.length < 5 ? "комнаты" : "комнат"}
                {data && ` · общая площадь пола ${formatNum(data.geometry.floor_area)} м²`}
              </div>
            </div>
          </div>

          {!data ? (
            <div className={styles.empty}>
              Постройте комнату и нажмите «Рассчитать смету» —
              <br />
              площади, вилка цены и ведомости появятся здесь.
            </div>
          ) : (
            <>
              {/* плитки геометрии */}
              <div className={styles.tiles}>
                <div className={styles.tile}>
                  <div className={styles.tileValue}>
                    {formatNum(data.geometry.floor_area)}
                    <span className={styles.tileUnit}>м²</span>
                  </div>
                  <div className={styles.tileLabel}>Пол</div>
                </div>
                <div className={styles.tile}>
                  <div className={styles.tileValue}>
                    {formatNum(data.geometry.ceiling_area)}
                    <span className={styles.tileUnit}>м²</span>
                  </div>
                  <div className={styles.tileLabel}>Потолок</div>
                </div>
                <div className={styles.tile}>
                  <div className={styles.tileValue}>
                    {formatNum(data.geometry.perimeter)}
                    <span className={styles.tileUnit}>м</span>
                  </div>
                  <div className={styles.tileLabel}>Периметр</div>
                </div>
                <div className={styles.tile}>
                  <div className={styles.tileValue}>
                    {formatNum(data.geometry.wall_area)}
                    <span className={styles.tileUnit}>м²</span>
                  </div>
                  <div className={styles.tileLabel}>Стены</div>
                </div>
              </div>

              {/* три итога: материалы / работы / итого × низкая/средняя/высокая */}
              <div className={styles.blockLabel}>Вилка стоимости</div>
              <table className={styles.summaryTable}>
                <thead>
                  <tr>
                    <th></th>
                    <th>Низкая</th>
                    <th>Средняя</th>
                    <th>Высокая</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Материалы</td>
                    <td>{formatPrice(data.summary.materials_min)}</td>
                    <td>{formatPrice(data.summary.materials_avg)}</td>
                    <td>{formatPrice(data.summary.materials_max)}</td>
                  </tr>
                  <tr>
                    <td>Работы</td>
                    <td>{formatPrice(data.summary.labor_min)}</td>
                    <td>{formatPrice(data.summary.labor_avg)}</td>
                    <td>{formatPrice(data.summary.labor_max)}</td>
                  </tr>
                  <tr className={styles.summaryTableTotalRow}>
                    <td>Итого</td>
                    <td>{formatPrice(data.summary.total_min)}</td>
                    <td>{formatPrice(data.summary.total_avg)}</td>
                    <td>{formatPrice(data.summary.total_max)}</td>
                  </tr>
                </tbody>
              </table>

              {(data.scope ?? scope) === "finish_only" && (
                <p className={styles.scopeNote}>
                  Смета охватывает только чистовую отделку — черновые работы не включены.
                </p>
              )}

              {/* Блок: Переключатель уровней цен + кнопки экспорта */}
              <div className={styles.exportControlsWrapper}>
                <div className={styles.rangeWrapper}>
                  {/* переключатель режима цен — суммы в таблице выше, здесь только подписи */}
                  <div className={styles.rangeRow}>
                    <div
                      className={`${styles.rangeCol} ${styles.rangeColClickable}`}
                      onClick={() => !isDragging && setPriceMode("min")}
                    >
                      <span className={`${styles.rangeCap} ${priceMode === "min" ? styles.rangeCapActive : ""}`}>
                        Минимум
                      </span>
                    </div>
                    <div
                      className={`${styles.rangeCol} ${styles.rangeColCenter} ${styles.rangeColClickable}`}
                      onClick={() => !isDragging && setPriceMode("avg")}
                    >
                      <span className={`${styles.rangeCap} ${priceMode === "avg" ? styles.rangeCapActive : ""}`}>
                        Средняя
                      </span>
                    </div>
                    <div
                      className={`${styles.rangeCol} ${styles.rangeColRight} ${styles.rangeColClickable}`}
                      onClick={() => !isDragging && setPriceMode("max")}
                    >
                      <span className={`${styles.rangeCap} ${priceMode === "max" ? styles.rangeCapActive : ""}`}>
                        Максимум
                      </span>
                    </div>
                  </div>

                  <div
                    ref={trackRef}
                    className={`${styles.rangeTrack} ${styles.rangeTrackCompact} ${isDragging ? styles.rangeTrackDragging : ""}`}
                    onPointerDown={handleTrackPointerDown}
                    onPointerMove={handleTrackPointerMove}
                    onPointerUp={handleTrackPointerUp}
                    onPointerCancel={handleTrackPointerUp}
                    style={{ marginBottom: '8px' }}
                  >
                    <span
                      className={`${styles.rangeEnd} ${priceMode === "min" && !isDragging ? styles.rangeEndActive : ""}`}
                      style={{ left: 0 }}
                    />
                    {/* На min/max точка легла бы точно на rangeEnd (разные размеры/центровка —
                        получалось наложение из двух кружков). Пока не тащим и стоим на краю,
                        просто прячем её — сам rangeEnd уже подсвечен активным. */}
                    {(isDragging || priceMode === "avg") && (
                      <span
                        className={styles.rangeDot}
                        style={{
                          left: `${dotVisualPos}%`,
                          transition: isDragging ? "none" : "left 0.2s ease",
                        }}
                      />
                    )}
                    <span
                      className={`${styles.rangeEnd} ${priceMode === "max" && !isDragging ? styles.rangeEndActive : ""}`}
                      style={{ right: 0 }}
                    />
                  </div>
                </div>
                
                <div className={`${styles.exportRow} ${styles.exportRowPadded}`}>
                  <button
                    className={styles.exportBtn}
                    onClick={() =>
                      data && import("../../utils/exportEstimate").then((m) => m.exportPdf(data, city, priceMode, materialOverrides))
                    }
                  >
                    Скачать PDF
                  </button>
                  <button
                    className={styles.exportBtn}
                    onClick={() =>
                      data && import("../../utils/exportEstimate").then((m) => m.exportXlsx(data, city, priceMode, materialOverrides))
                    }
                  >
                    Экспорт в Excel
                  </button>
                  <button className={styles.exportBtn} onClick={() => window.print()}>
                    Печать
                  </button>
                </div>
              </div>

              {/* вкладки */}
              <div className={styles.tabs}>
                <button
                  className={`${styles.tab} ${tab === "materials" ? styles.tabActive : ""}`}
                  onClick={() => setTab("materials")}
                >
                  Ведомость материалов
                </button>
                <button
                  className={`${styles.tab} ${tab === "labor" ? styles.tabActive : ""}`}
                  onClick={() => setTab("labor")}
                >
                  План работ
                </button>
              </div>

              {tab === "materials" || (data.scope ?? scope) === "finish_only" || laborByStage.size <= 1 ? (
                <EstimateLedger rows={tab === "materials" ? materialRows : laborRows} />
              ) : (
                <>
                  {(["rough", "pre_finish", "finish"] as LaborStage[])
                    .filter((stage) => laborByStage.has(stage))
                    .map((stage) => {
                      const items = laborByStage.get(stage)!;
                      const stageTotal = items.reduce((s, x) => s + x.activeTotal, 0);
                      return (
                        <div key={stage}>
                          <div className={styles.stageHeader}>{STAGE_LABELS[stage]}</div>
                          <EstimateLedger rows={items.map(laborItemToRow)} />
                          <div className={styles.stageSubtotal}>{rub(Math.round(stageTotal))}</div>
                        </div>
                      );
                    })}
                </>
              )}

              <div className={styles.sectionTotal}>
                <span className={styles.sectionTotalLabel}>
                  Итого по разделу «{tab === "materials" ? "Ведомость материалов" : "План работ"}»
                </span>
                <span className={styles.sectionTotalValue}>{formatPrice(sectionTotal)}</span>
              </div>

              {data.hidden_works && data.hidden_works.items.length > 0 && (
                <div className={styles.hiddenSection}>
                  <div className={styles.blockLabel}>Скрытые работы · возможные доплаты</div>
                  <p className={styles.hiddenNote}>{data.hidden_works.note}</p>
                  <table className={styles.hiddenTable}>
                    <thead>
                      <tr>
                        <th>Работа</th>
                        <th>Причина</th>
                        <th>Объём</th>
                        <th>Ориентировочная вилка</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.hidden_works.items.map((item, i) => (
                        <tr key={i}>
                          <td>{item.service}</td>
                          <td className={styles.hiddenReason}>{item.reason}</td>
                          <td className={styles.hiddenVol}>
                            {formatQty(item.volume)} {item.unit}
                          </td>
                          <td className={styles.hiddenRange}>
                            {formatPrice(item.total_min)} — {formatPrice(item.total_max)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <div className={styles.hiddenTotal}>
                    <span>Итого возможных доплат</span>
                    <span>
                      {formatPrice(data.hidden_works.total_min)} — {formatPrice(data.hidden_works.total_max)}
                    </span>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </aside>
    </div>
  );
}