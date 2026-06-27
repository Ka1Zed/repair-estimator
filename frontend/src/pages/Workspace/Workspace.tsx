import { useCallback, useEffect, useMemo, useState } from "react";
import styles from "./Workspace.module.css";
import { exportPdf, exportXlsx } from '../../utils/exportEstimate';

import RoomsList from "../../components/RoomsList";
import RoomPolygonEditor from "../../components/RoomPolygonEditor";
import RoomPointsTable from "../../components/RoomPointsTable";
import BlueprintUpload from "../../components/BlueprintUpload";
import OpeningsForm from "../../components/OpeningsForm";
import { RoomTypeSelector } from "../../components/RoomTypeSelector";
import { RepairOptionsForm } from "../../components/RepairOptionsForm/RepairOptionsForm";

import type { MaterialItem } from "../../components/EstimateTables/MaterialsTable";
import type { LaborItem } from "../../components/EstimateTables/LaborTable";
import type { SummaryData } from "../../components/EstimateSummary";
import { EstimateLedger, type LedgerRow } from "../../components/EstimateLedger/EstimateLedger";

import { useProjectStore } from "../../store/projectStore";
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
}

const formatPrice = (price: number) => `${Math.round(price).toLocaleString("ru-RU")} ₽`;
const formatNum = (n: number) =>
  n.toLocaleString("ru-RU", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const formatQty = (n: number) => n.toLocaleString("ru-RU", { maximumFractionDigits: 1 });
const rub = (n: number) => `${n.toLocaleString("ru-RU")} ₽`;

const regionLabel = (region?: string | null) => region ?? "базовая цена";

export function Workspace() {
  const rooms = useProjectStore((s) => s.rooms);
  const city = useProjectStore((s) => s.city);
  const setCity = useProjectStore((s) => s.setCity);
  const repairType = useProjectStore((s) => s.repair_type);
  const repairOptions = useProjectStore((s) => s.repair_options);
  const activeRoomIndex = useProjectStore((s) => s.activeRoomIndex);
  const activeRoom = rooms[activeRoomIndex];
  const setHeight = useProjectStore((s) => s.setHeight);

  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<EstimateResponse | null>(null);
  const [tab, setTab] = useState<"materials" | "labor">("materials");
  const [regions, setRegions] = useState<string[]>([]);

  
  useEffect(() => {
    apiClient
      .fetchRegions()
      .then((res) => setRegions(res.regions))
      .catch((err) => console.error("Не удалось загрузить список городов:", err));
  }, []);

  const cityOptions = useMemo(
    () => (regions.includes(city) ? regions : [city, ...regions]),
    [regions, city],
  );

  // silent=true — авто-пересчёт по дебаунсу: молча пропускаем невалидное состояние,
  // не пугаем пользователя ошибкой, пока он редактирует.
  const runCalculate = useCallback(
    async (silent: boolean) => {
      const allValid = rooms.every(
        (r) => r.points.length >= 3 && r.height !== "" && Number(r.height) > 0,
      );
      if (!allValid) {
        if (!silent) {
          setError("У каждой комнаты нужны минимум 3 точки и высота потолка больше нуля.");
        }
        return;
      }

      setIsLoading(true);
      setError(null);
      try {
        const payload = {
          city,
          repair_type: repairType,
          repair_options: repairOptions,
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
          })),
        };
        const res = (await calculateEstimate(payload)) as EstimateResponse;
        setData(res);
      } catch (err) {
        console.error(err);
        if (!silent) {
          setError("Не удалось рассчитать смету. Проверьте, что бэкенд запущен.");
        }
      } finally {
        setIsLoading(false);
      }
    },
    [rooms, city, repairType, repairOptions],
  );

 
  useEffect(() => {
    const timer = setTimeout(() => runCalculate(true), 500);
    return () => clearTimeout(timer);
  }, [runCalculate]);

  const handleCalculate = () => runCalculate(false);

  // Слайдер вилки: позиция средней между min и max
  const avgPos = useMemo(() => {
    if (!data) return 50;
    const { total_min, total_avg, total_max } = data.summary;
    if (total_max <= total_min) return 50;
    return ((total_avg - total_min) / (total_max - total_min)) * 100;
  }, [data]);

  const sectionTotal = useMemo(() => {
    if (!data) return 0;
    const items = tab === "materials" ? data.materials : data.labor;
    return items.reduce((sum, i) => sum + (i.total_avg ?? 0), 0);
  }, [data, tab]);

  const materialRows: LedgerRow[] = useMemo(
    () =>
      (data?.materials ?? ([] as MaterialItem[])).map((m) => ({
        name: m.name,
        volume: `${formatQty(m.quantity)} ${m.unit}`,
        price: rub(m.price_avg),
        details: [
          { label: "Цена за единицу", value: rub(m.price_avg) },
          { label: "Итог по позиции", value: rub(m.total_avg) },
          { label: "Источник цены", value: m.source },
          { label: "Регион", value: regionLabel(m.region) },
          ...(m.updated_at ? [{ label: "Обновлено", value: m.updated_at }] : []),
        ],
      })),
    [data],
  );

  const laborRows: LedgerRow[] = useMemo(
    () =>
      (data?.labor ?? ([] as LaborItem[])).map((l) => ({
        name: l.service,
        subtitle: l.specialist,
        volume: `${formatQty(l.volume)} ${l.unit}`,
        price: rub(l.price_avg),
        details: [
          { label: "Специалист", value: l.specialist },
          { label: "Цена за единицу", value: rub(l.price_avg) },
          { label: "Итог по позиции", value: rub(l.total_avg) },
          { label: "Источник цены", value: l.source },
          { label: "Регион", value: regionLabel(l.region) },
        ],
      })),
    [data],
  );

  return (
    <div className={styles.page}>
      {/* ===== ЛЕВО: редактор ===== */}
      <section className={styles.left}>
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

        {/* высота потолка + класс ремонта — сразу под холстом */}
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
                value={activeRoom?.height ?? ""}
                onChange={(e) => setHeight(e.target.value)}
              />
              <span className={styles.heightUnit}>м</span>
            </div>
          </div>
          <RepairOptionsForm />
        </div>

        <div className={styles.block}>
          <div className={styles.blockLabel}>Состав работ · тип комнаты</div>
          <RoomTypeSelector />
        </div>

        <div className={styles.block}>
          <OpeningsForm />
        </div>

        {/* координаты углов спрятаны под тогл, чтобы не загромождать */}
        <details className={styles.pointsDetails}>
          <summary className={styles.pointsSummary}>Координаты углов</summary>
          <div className={styles.pointsBody}>
            <RoomPointsTable />
          </div>
        </details>

        {/* загрузка чертежа — ниже, как вспомогательный сценарий */}
        <div className={styles.block}>
          <BlueprintUpload />
        </div>

        <button className={styles.calcBtn} onClick={handleCalculate} disabled={isLoading}>
          {isLoading ? "Считаем…" : "Рассчитать смету"}
        </button>
        {error && <div className={styles.error}>{error}</div>}
      </section>

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
           <div className={styles.exportRow}>
              <button 
                className={styles.exportBtn} 
                onClick={() => data && exportPdf(data, city, repairType)} 
                disabled={!data}
              >
                Скачать PDF
              </button>
              <button 
                className={styles.exportBtn} 
                onClick={() => data && exportXlsx(data)} 
                disabled={!data}
              >
                Экспорт в Excel
              </button>
              <button 
                className={styles.exportBtn} 
                onClick={() => window.print()} 
                disabled={!data}
              >
                Печать
              </button>
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

              {/* вилка стоимости */}
              <div className={styles.blockLabel}>Вилка стоимости</div>
              <div className={styles.rangeRow}>
                <div className={styles.rangeCol}>
                  <span className={styles.rangeCap}>Минимум</span>
                  <span className={styles.rangeValue}>{formatPrice(data.summary.total_min)}</span>
                </div>
                <div className={`${styles.rangeCol} ${styles.rangeColCenter}`}>
                  <span className={`${styles.rangeCap} ${styles.rangeCapAccent}`}>Средняя</span>
                  <span className={`${styles.rangeValue} ${styles.rangeValueMain}`}>
                    {formatPrice(data.summary.total_avg)}
                  </span>
                </div>
                <div className={`${styles.rangeCol} ${styles.rangeColRight}`}>
                  <span className={styles.rangeCap}>Максимум</span>
                  <span className={styles.rangeValue}>{formatPrice(data.summary.total_max)}</span>
                </div>
              </div>
              <div className={styles.rangeTrack}>
                <span className={styles.rangeEnd} style={{ left: "0%" }} />
                <span className={styles.rangeDot} style={{ left: `${avgPos}%` }} />
                <span className={styles.rangeEnd} style={{ left: "100%" }} />
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
              
              <EstimateLedger rows={tab === "materials" ? materialRows : laborRows} />

              <div className={styles.sectionTotal}>
                <span className={styles.sectionTotalLabel}>
                  Итого по разделу «{tab === "materials" ? "Ведомость материалов" : "План работ"}»
                </span>
                <span className={styles.sectionTotalValue}>{formatPrice(sectionTotal)}</span>
              </div>
            </>
          )}
        </div>
      </aside>
    </div>
  );
}
