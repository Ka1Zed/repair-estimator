import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import styles from "./Workspace.module.css";
import type { Navigate } from "../../App";
import type { ProjectPayload } from "../../types/project";

import RoomsList from "../../components/RoomsList";
import RoomPolygonEditor from "../../components/RoomPolygonEditor";
import RoomPointsTable from "../../components/RoomPointsTable";
import BlueprintUpload from "../../components/BlueprintUpload";
import OpeningsForm from "../../components/OpeningsForm";
import { WorksPanel } from "../../components/WorksPanel/WorksPanel";

import type { MaterialItem, LaborItem, LaborStage, HiddenWorks } from "../../types/estimate";
import type { SummaryData } from "../../components/EstimateSummary";
import { EstimateLedger, type LedgerRow, type LedgerRowVariant } from "../../components/EstimateLedger/EstimateLedger";
import { useProjectStore, type EstimateScope, type CeilingShapeType } from "../../store/projectStore";
import { useBackendStatus } from "../../store/backendStatus";
import { roomHasInvalidOpenings } from "../../utils/openingValidation";
import { hasSelfIntersection, validateHeight } from "../../utils/polygonValidation";
import { calculateEstimate } from "../../api/estimates";
import { apiClient } from "../../api/client";
import { Select } from "../../components/ui/Select";
import { roomsToCalcPayload } from "../../utils/roomsToPayload";
import { hasTierVariants } from "../../utils/tier";

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
// Фасовка от парсера приходит с float-хвостом (8.999975… л, 1.974994… м²) — округляем
// до 2 знаков, чтобы не показывать мусор пользователю, но сохранить реальную дробность
// упаковки (напр. 1.97 м² в пачке ламината). Экспорт уже чистит это через fmtQty.
const formatPackage = (n: number) => n.toLocaleString("ru-RU", { maximumFractionDigits: 2 });
const rub = (n: number) => `${n.toLocaleString("ru-RU")} ₽`;

// Регион, по которому реально взялась цена; null → нерегиональный источник
// (парсер отдаёт один и тот же каталог на все города, см. docs/price-sources.md).
// Мегастрой и базовый Леман физически используют домен kazan.* при ЛЮБОМ выбранном
// городе (проверено вживую: тот же source_url для Москвы/Новосибирска/Казани) —
// подставлять "Казань" им всегда было бы неправдой. Честно можно показать город
// только когда пользователь и правда выбрал Казань — тогда это совпадает с фактом.
// "базовая цена" — только для настоящего seed-резерва (нет живого источника вообще).
// Если источник — реальный парсер (Мегастрой/Леман), просто не привязанный к городу,
// так его называть неверно: это не "запасной" вариант, а актуальная живая цена.
const regionLabel = (
  region: string | null | undefined,
  sourceUrl: string | null | undefined,
  selectedCity: string,
  source: string,
) => {
  if (region) return region;
  if (selectedCity === "Казань" && sourceUrl?.includes("kazan.")) return "Казань";
  return source === "seed" ? "базовая цена" : "не привязан к городу";
};

// "company_price" — источник rembrigada116.ru (казанская компания), но так
// исторически называется в БД (см. rembrigada_parser.py) — не показываем сырой
// внутренний код клиенту.
const LABOR_SOURCE_NAMES: Record<string, string> = { company_price: "rembrigada116.ru" };
const laborSourceName = (source: string) => LABOR_SOURCE_NAMES[source] ?? source;

// Резерв на непредвиденные (CONTINGENCY, backend/app/services/repair_coeffs_service.py),
// уже включён в "Итог по позиции" — поэтому итог не равен цене за единицу × кол-во.
const CONTINGENCY_PCT: Record<PriceMode, number> = { min: 10, avg: 12, max: 15 };

const CEILING_SHAPE_OPTIONS = [
  { value: "flat", label: "Плоский" },
  { value: "multilevel", label: "Многоуровневый" },
  { value: "attic_slope", label: "Мансардный скат" },
];

export type PriceMode = "min" | "avg" | "max";

interface WorkspaceProps {
  onNavigate: Navigate;
  projectId?: number;
  shareToken?: string;
  projectName?: string;
}

export function Workspace({
  onNavigate,
  projectId,
  shareToken: initialShareToken,
  projectName: initialProjectName,
}: WorkspaceProps) {
  const rooms = useProjectStore((s) => s.rooms);
  const city = useProjectStore((s) => s.city);
  const setCity = useProjectStore((s) => s.setCity);
  const scope = useProjectStore((s) => s.scope);
  const setScope = useProjectStore((s) => s.setScope);
  const store = useProjectStore((s) => s.store);
  const setStore = useProjectStore((s) => s.setStore);
  const activeRoomIndex = useProjectStore((s) => s.activeRoomIndex);
  const activeRoom = rooms[activeRoomIndex];
  const setHeight = useProjectStore((s) => s.setHeight);
  const setCeilingShape = useProjectStore((s) => s.setCeilingShape);

  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<EstimateResponse | null>(null);
  const [tab, setTab] = useState<"materials" | "labor">("materials");
  const [regions, setRegions] = useState<string[]>([]);
  const [stores, setStores] = useState<{ name: string; available: boolean }[]>([]);
  const [storeResetNotice, setStoreResetNotice] = useState<string | null>(null);

  // project save / share state
  const [savedProjectId, setSavedProjectId] = useState<number | null>(projectId ?? null);
  const [shareToken, setShareToken] = useState<string | null>(initialShareToken ?? null);
  const [projectName, setProjectName] = useState(initialProjectName ?? "");
  const [saveOpen, setSaveOpen] = useState(false);
  const [saveLoading, setSaveLoading] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [copiedShare, setCopiedShare] = useState(false);

  const roomsToPayload = useCallback((): ProjectPayload => ({
    name: projectName.trim() || "Проект без названия",
    city,
    scope,
    rooms: rooms.map((r) => ({
      name: r.name,
      room_type: r.room_type,
      height: Number(r.height),
      points: r.points.map((p) => ({ x: Number(p.x), y: Number(p.y) })),
      openings: r.openings.map((op) => ({
        type: op.type,
        width: Number(op.width),
        height: Number(op.height),
      })),
      works: r.works as unknown as Record<string, unknown>,
      ceiling_shape: {
        type: r.ceilingShape.type,
        levels: r.ceilingShape.levels != null ? Number(r.ceilingShape.levels) : null,
        step_height_m: r.ceilingShape.step_height_m != null ? Number(r.ceilingShape.step_height_m) : null,
        slope_deg: r.ceilingShape.slope_deg != null ? Number(r.ceilingShape.slope_deg) : null,
      },
    })),
  }), [projectName, city, scope, rooms]);

  const handleSave = useCallback(async () => {
    setSaveLoading(true);
    setSaveError(null);
    try {
      const payload = roomsToPayload();
      if (savedProjectId !== null) {
        const updated = await apiClient.updateProject(savedProjectId, payload);
        setShareToken(updated.share_token);
      } else {
        const created = await apiClient.createProject(payload);
        setSavedProjectId(created.id);
        setShareToken(created.share_token);
      }
      setSaveOpen(false);
    } catch {
      setSaveError("Не удалось сохранить. Проверьте, что бэкенд запущен.");
    } finally {
      setSaveLoading(false);
    }
  }, [roomsToPayload, savedProjectId]);

  const handleCopyShare = useCallback(() => {
    if (!shareToken) return;
    navigator.clipboard.writeText(`${location.origin}/share/${shareToken}`).then(() => {
      setCopiedShare(true);
      setTimeout(() => setCopiedShare(false), 2000);
    });
  }, [shareToken]);

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

  // Работы уровней не имеют (#419): SKU-вариантов у услуги нет, вилка это лишь разброс
  // цены одного подрядчика по прайс-листам, не выбор комплектации — закрепление уровня
  // по услуге убрано. Глобальный ползунок min/avg/max по-прежнему двигает итог.

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

  // Доступность магазинов материалов (Мегастрой/Леман) в выбранном городе (#365):
  // Мегастрой и Леман покрывают разные города по-разному (см. docs/price-sources.md).
  // Сброс невалидного выбора магазина (если он стал недоступен после смены города)
  // делаем прямо в колбэке ответа, а не отдельным эффектом-синхронизацией — иначе
  // setState вызывается синхронно в теле эффекта (react-hooks/set-state-in-effect).
  useEffect(() => {
    apiClient
      .fetchStores(city)
      .then((res) => {
        setStores(res.stores);
        const found = store && res.stores.find((s) => s.name === store);
        if (found && !found.available) {
          setStore(null);
          setStoreResetNotice(`«${store}» недоступен в городе «${city}» — выбор сброшен на «Любой».`);
          setTimeout(() => setStoreResetNotice(null), 5000);
        }
      })
      .catch((err) => console.error("Не удалось загрузить список магазинов:", err));
  }, [city, store, setStore]);

  const storeOptions = useMemo(
    () => [
      { value: "", label: "Любой" },
      ...stores.map((s) => ({
        value: s.name,
        label: s.name,
        disabled: !s.available,
        title: s.available ? undefined : `${s.name} сейчас недоступен в городе «${city}»`,
      })),
    ],
    [stores, city],
  );

  // Порядковый номер запроса расчёта: авто-пересчёт по дебаунсу и клик по кнопке
  // могут запустить несколько запросов подряд. Если ответ на старый запрос придёт
  // позже нового (сеть/нагрузка), он не должен перезаписать свежую смету — сверяем
  // номер перед setState и игнорируем устаревший ответ.
  const calcSeqRef = useRef(0);

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

      const seq = ++calcSeqRef.current;
      setIsLoading(true);
      setError(null);
      try {
        const payload = {
          city,
          scope,
          tier: "avg",
          stores: store ? [store] : null,
          rooms: roomsToCalcPayload(rooms),
        };
        // Один запрос вместо трёх параллельных (#349): бэкенд теперь сам отдаёт
        // min_item/avg_item/max_item на каждой строке материала — для 6 finish_key-позиций
        // (ламинат, покраска стен/потолка, плитка, обои, розетка, #331) это разные товары
        // (name/source_url), для остальных — тот же товар со своей точкой коридора.
        // «Вилка стоимости» материалов строится из этих же *_item.total (не из
        // summary.materials_min/max бэкенда — та вилка про источники ВНУТРИ resolved-tier
        // товара, а не про эконом/премиум SKU, см. docs/api.md).
        const res = (await calculateEstimate(payload)) as EstimateResponse;

        // Пришёл ответ на устаревший запрос — уже летит более свежий, игнорируем.
        if (seq !== calcSeqRef.current) return;

        const materials = res.materials;
        const materialsMin = materials.reduce((s, m) => s + (m.min_item?.total ?? 0), 0);
        const materialsMax = materials.reduce((s, m) => s + (m.max_item?.total ?? 0), 0);
        const summary = {
          ...res.summary,
          materials_min: materialsMin,
          materials_max: materialsMax,
          total_min: materialsMin + res.summary.labor_min,
          total_max: materialsMax + res.summary.labor_max,
        };

        setData({ ...res, summary, materials });
        setPriceMode("avg");
        setMaterialOverrides({});
      } catch (err) {
        if (seq !== calcSeqRef.current) return;
        console.error(err);
        if (!silent) {
          setError("Не удалось рассчитать смету. Проверьте, что бэкенд запущен.");
        }
      } finally {
        // Гасим индикатор загрузки только для самого свежего запроса.
        if (seq === calcSeqRef.current) setIsLoading(false);
      }
    },
    [rooms, city, scope, store],
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

      // Уровни Эконом/Стандарт/Премиум показываем ТОЛЬКО у finish_key-позиций
      // (ламинат/плитка/покраска/обои/розетка, #331), где min/avg/max_item — реально
      // разные товары со своим source_url. У коммодити-материалов (светильник, кабель,
      // труба, плинтус, грунт/шпаклёвка) товар один на все tier — вилка это лишь разброс
      // цены одного товара по магазинам, а не выбор уровня. Для них псевдо-уровни и
      // закрепление не показываем, вместо этого даём диапазон «по магазинам» (#419).
      const tiered = hasTierVariants(m);
      const variants: LedgerRowVariant[] = [];
      if (tiered) {
        if (m.min_item) variants.push({ mode: "min", title: "Эконом", name: m.min_item.name, price: rub(Math.round(m.min_item.price)), url: m.min_item.source_url, onClick: () => toggleMaterialOverride(i, "min") });
        if (m.avg_item) variants.push({ mode: "avg", title: "Стандарт", name: m.avg_item.name, price: rub(Math.round(m.avg_item.price)), url: m.avg_item.source_url, onClick: () => toggleMaterialOverride(i, "avg") });
        if (m.max_item) variants.push({ mode: "max", title: "Премиум", name: m.max_item.name, price: rub(Math.round(m.max_item.price)), url: m.max_item.source_url, onClick: () => toggleMaterialOverride(i, "max") });
      }

      // Диапазон цены одного товара по магазинам (не уровни) — для коммодити-позиций,
      // когда границы вилки реально разные (#419).
      const priceRange =
        !tiered && m.price_max > m.price_min
          ? `${rub(Math.round(m.price_min))} – ${rub(Math.round(m.price_max))}`
          : null;

      const activeVariant = effectiveMode === "min" ? m.min_item : effectiveMode === "max" ? m.max_item : m.avg_item;
      const activeName = activeVariant?.name ?? m.name;
      const activePrice = activeVariant ? activeVariant.price : m.price_avg * scale;
      const activeTotal = activeVariant ? activeVariant.total : m.total_avg * scale;
      const activeUrl = activeVariant?.source_url ?? m.source_url;
      const activeSource = activeVariant?.source ?? m.source;

      // Фасовка/единица/упаковки выбранного уровня (#349): у finish_key-позиций
      // товар меняется по tier, и фасовка своя (9 л против 10 л, плинтус 2.5 м
      // против 3 м). Берём из активного варианта, откат на общую строку для старых
      // ответов/материалов без вариантов. quantity/packs у варианта могут быть 0
      // (no-price) — тогда тоже откат.
      const activePackageSize = activeVariant?.package_size || m.package_size;
      const activeUnit = activeVariant?.unit || m.unit;
      const activeVolume = activeVariant?.quantity || m.quantity;
      const activePacks = activeVariant?.packs || m.packs;

      const combinedSources = !tiered && m.sources && m.sources.length > 1 ? m.sources : null;
      const sourceLabel = combinedSources ? combinedSources.join(", ") : activeSource;
      const sourceCount = combinedSources ? combinedSources.length : 1;

      return { m, effectiveMode, activeName, activePrice, activeTotal, activeUrl, activeSource, activePackageSize, activeUnit, activeVolume, activePacks, sourceLabel, sourceCount, variants, priceRange };
    });
  }, [data, priceScale, priceMode, materialOverrides, toggleMaterialOverride]);

  const materialRows: LedgerRow[] = useMemo(
    () =>
      materialsActive.map(({ m, effectiveMode, activeName, activePrice, activeTotal, activeUrl, activeSource, activePackageSize, activeUnit, activeVolume, activePacks, sourceLabel, sourceCount, variants, priceRange }, i) => ({
        name: activeName,
        volume: `${formatQty(activeVolume)} ${activeUnit}`,
        price: rub(Math.round(activePrice)),
        total: rub(Math.round(activeTotal)),
        activeMode: effectiveMode,
        isOverridden: materialOverrides[i] !== undefined && materialOverrides[i] !== priceMode,
        variants: variants.length > 0 ? variants : undefined,
        details: [
          { label: "Базовое кол-во", value: `${formatQty(m.base_quantity)} ${activeUnit}` },
          { label: "Запас", value: `×${m.waste_factor} (+${Math.round((m.waste_factor - 1) * 100)}%)` },
          { label: "Упаковок", value: `${activePacks} × ${formatPackage(activePackageSize)} ${activeUnit}` },
          { label: "Итого кол-во", value: `${formatQty(activeVolume)} ${activeUnit}` },
          { label: "Цена за единицу", value: rub(Math.round(activePrice)) },
          ...(priceRange ? [{ label: "Цена по магазинам", value: priceRange }] : []),
          {
            label: "Итог по позиции",
            value: `${rub(Math.round(activeTotal))} (с резервом +${CONTINGENCY_PCT[effectiveMode]}%)`,
          },
          {
            label: sourceCount > 1 ? "Источники цены" : "Источник цены",
            value: sourceLabel,
            ...(variants.length > 0 ? {} : { url: activeUrl }),
          },
          { label: "Регион", value: regionLabel(m.region, activeUrl, city, activeSource) },
          ...(m.updated_at
            ? [{ label: "Обновлено", value: new Date(m.updated_at).toLocaleDateString("ru-RU") }]
            : []),
        ],
      })),
    [materialsActive, materialOverrides, city, priceMode],
  );

  // Работы с учётом эффективного уровня по каждой строке. В отличие от материалов,
  // у работы нет альтернативного исполнителя по tier — только цена внутри своего
  // коридора (price_min/avg/max), уже посчитанного бэкендом для строки.
  const laborActive = useMemo(() => {
    const scale = priceScale("labor");

    return (data?.labor ?? []).map((l) => {
      // У работ нет SKU-вариантов уровня (#419): показываем цену выбранного глобального
      // режима, а разброс price_min/price_max — как диапазон «по подрядчикам», не как
      // выбор Эконом/Премиум. Закрепления уровня по услуге нет.
      const hasCorridor = l.price_min != null && l.price_max != null;

      const activePrice = !hasCorridor
        ? l.price_avg * scale
        : priceMode === "min"
          ? l.price_min!
          : priceMode === "max"
            ? l.price_max!
            : l.price_avg;
      const activeTotal = !hasCorridor
        ? l.total_avg * scale
        : priceMode === "min"
          ? (l.total_min ?? l.total_avg)
          : priceMode === "max"
            ? (l.total_max ?? l.total_avg)
            : l.total_avg;

      // Диапазон цены услуги по разным подрядчикам из l.sources (границы вилки), когда
      // они реально различаются — информационно, без выбора уровня.
      const priceRange =
        hasCorridor && l.price_max! > l.price_min!
          ? `${rub(Math.round(l.price_min!))} – ${rub(Math.round(l.price_max!))}`
          : null;

      const sourceCount = l.sources?.length ?? (l.source ? 1 : 0);
      const sourceLabel =
        l.sources && l.sources.length > 1
          ? l.sources.map(laborSourceName).join(", ")
          : laborSourceName(l.source);

      return { l, activePrice, activeTotal, priceRange, sourceLabel, sourceCount };
    });
  }, [data, priceScale, priceMode]);

  const laborItemToRow = useCallback(
    ({ l, activePrice, activeTotal, priceRange, sourceLabel, sourceCount }: (typeof laborActive)[number]): LedgerRow => ({
      name: l.service,
      subtitle: l.specialist,
      volume: `${formatQty(l.volume)} ${l.unit}`,
      price: rub(Math.round(activePrice)),
      total: rub(Math.round(activeTotal)),
      activeMode: priceMode,
      details: [
        { label: "Специалист", value: l.specialist },
        { label: "Цена за единицу", value: rub(Math.round(activePrice)) },
        ...(priceRange ? [{ label: "Цена по подрядчикам", value: priceRange }] : []),
        {
          label: "Итог по позиции",
          value: `${rub(Math.round(activeTotal))} (с резервом +${CONTINGENCY_PCT[priceMode]}%)`,
        },
        {
          label: sourceCount > 1 ? "Источники цены" : "Источник цены",
          value: sourceLabel,
          ...(sourceCount > 1 ? {} : { url: l.source_url }),
        },
        { label: "Регион", value: regionLabel(l.region, l.source_url, city, l.source) },
      ],
    }),
    [city, priceMode],
  );

  const laborRows: LedgerRow[] = useMemo(
    () => laborActive.map((item) => laborItemToRow(item)),
    [laborActive, laborItemToRow],
  );

  const hasMixedOverrides = useMemo(
    () => Object.entries(materialOverrides).some(([, mode]) => mode !== priceMode),
    [materialOverrides, priceMode],
  );

  const clearAllOverrides = useCallback(() => {
    setMaterialOverrides({});
  }, []);

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
        <div className={styles.projectNav}>
          <div className={styles.eyebrow}>Проект · план помещения</div>
          <button className={styles.myProjectsBtn} onClick={() => onNavigate({ type: "projects" })}>
            Мои проекты
          </button>
        </div>
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
          <div className={styles.cityField}>
            <div className={styles.blockLabel}>Магазин</div>
            <Select
              variant="underline"
              ariaLabel="Магазин материалов"
              value={store ?? ""}
              options={storeOptions}
              onChange={(v) => setStore(v || null)}
            />
            {storeResetNotice && (
              <div className={styles.error} style={{ marginTop: 4, fontSize: 12 }}>
                {storeResetNotice}
              </div>
            )}
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
          <div className={styles.cityField}>
            <div className={styles.blockLabel}>Форма потолка</div>
            <Select
              variant="underline"
              ariaLabel="Форма потолка"
              value={activeRoom?.ceilingShape.type ?? "flat"}
              options={CEILING_SHAPE_OPTIONS}
              onChange={(v) =>
                setCeilingShape({
                  type: v as CeilingShapeType,
                  levels: null,
                  step_height_m: null,
                  slope_deg: null,
                })
              }
            />
            {activeRoom?.ceilingShape.type === "multilevel" && (
              <div style={{ display: "flex", gap: 16, marginTop: 4 }}>
                <div className={styles.heightField}>
                  <span className={styles.heightUnit}>Уровней короба</span>
                  <input
                    className={styles.heightInput}
                    type="number"
                    step="1"
                    min="1"
                    max="5"
                    placeholder="1"
                    value={activeRoom.ceilingShape.levels ?? ""}
                    onChange={(e) =>
                      setCeilingShape({ levels: e.target.value === "" ? null : Number(e.target.value) })
                    }
                  />
                </div>
                <div className={styles.heightField}>
                  <span className={styles.heightUnit}>Высота грани, м</span>
                  <input
                    className={styles.heightInput}
                    type="number"
                    step="0.01"
                    min="0.01"
                    max="1"
                    placeholder="0.12"
                    value={activeRoom.ceilingShape.step_height_m ?? ""}
                    onChange={(e) =>
                      setCeilingShape({ step_height_m: e.target.value === "" ? null : Number(e.target.value) })
                    }
                  />
                </div>
              </div>
            )}
            {activeRoom?.ceilingShape.type === "attic_slope" && (
              <div className={styles.heightField} style={{ marginTop: 4 }}>
                <span className={styles.heightUnit}>Угол ската, °</span>
                <input
                  className={styles.heightInput}
                  type="number"
                  step="1"
                  min="0"
                  max="84"
                  placeholder="0"
                  value={activeRoom.ceilingShape.slope_deg ?? ""}
                  onChange={(e) =>
                    setCeilingShape({ slope_deg: e.target.value === "" ? null : Number(e.target.value) })
                  }
                />
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
              <button
                className={`${styles.scopeBtn} ${scope === "rough_only" ? styles.scopeBtnActive : ""}`}
                onClick={() => setScope("rough_only")}
              >
                Только черновая
              </button>
            </div>
          </div>
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

        <div className={styles.saveArea}>
          {saveOpen ? (
            <div className={styles.saveForm}>
              <input
                className={styles.saveInput}
                placeholder="Название проекта"
                value={projectName}
                onChange={(e) => setProjectName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSave()}
              />
              <button
                className={styles.saveConfirmBtn}
                onClick={handleSave}
                disabled={saveLoading}
              >
                {saveLoading ? "Сохраняем…" : savedProjectId ? "Обновить" : "Сохранить"}
              </button>
              <button className={styles.saveCancelBtn} onClick={() => setSaveOpen(false)}>
                Отмена
              </button>
            </div>
          ) : (
            <button className={styles.saveBtn} onClick={() => setSaveOpen(true)}>
              {savedProjectId ? "Обновить проект" : "Сохранить проект"}
            </button>
          )}
          {saveError && <div className={styles.saveError}>{saveError}</div>}
          {shareToken && !saveOpen && (
            <button className={styles.shareBtn} onClick={handleCopyShare}>
              {copiedShare ? "Скопировано!" : "Поделиться ссылкой"}
            </button>
          )}
        </div>
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

              {(data.scope ?? scope) === "rough_only" && (
                <p className={styles.scopeNote}>
                  Смета охватывает только черновую и предчистовую подготовку — чистовая
                  отделка не включена.
                </p>
              )}

              {(data.scope ?? scope) === "rough_and_finish" && (
                <p className={styles.scopeNote}>
                  Некоторые работы и материалы (грунтовка, стартовая шпаклёвка стен,
                  прокладка кабеля, монтаж труб) нужны и на черновом, и на чистовом этапе,
                  поэтому здесь они учтены один раз. Из-за этого сумма отдельных смет
                  «только черновая» и «только чистовая» получается больше, чем эта общая
                  смета — это не ошибка расчёта.
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

                  {hasMixedOverrides && (
                    <div className={styles.mixedOverrideHint}>
                      <span className={styles.mixedOverrideIcon}>⚠</span>
                      <span>Часть позиций закреплена на отдельном уровне</span>
                      <button className={styles.resetOverridesBtn} onClick={clearAllOverrides}>
                        Сбросить
                      </button>
                    </div>
                  )}
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
                  <div className={styles.hiddenTableWrap}>
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
                  </div>
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