import { useState, useRef, useEffect } from "react";
import type { BlueprintResult } from "./BlueprintUpload";
import styles from "./BlueprintReview.module.css";

interface NormPoint {
  nx: number;
  ny: number;
}

interface Props {
  imageUrl: string;
  result: BlueprintResult;
  onApply: (points: { x: number; y: number }[], height: number | null) => void;
  onCancel: () => void;
}

const SVG_W = 400;
// Высота SVG-полотна по умолчанию (пока не известны реальные пропорции фото).
// Как только картинка грузится, подгоняем под её реальный aspect ratio (см. useEffect
// ниже) — иначе при preserveAspectRatio="xMidYMid meet" появляется леттербокс, и
// nx*SVG_W / ny*SVG_H масштабируют оси по-разному (см. #297: демо 4×3м выходило как 4.07×2.95).
const DEFAULT_SVG_H = 300;

function computeGeometry(result: BlueprintResult, svgH: number): { points: NormPoint[]; mPerPx: number | null } {
  const raw = result.points;
  if (raw.length === 0) return { points: [], mPerPx: null };

  const hasNorm = raw.every((p) => p.nx != null && p.ny != null);

  if (hasNorm) {
    const pts = raw.map((p) => ({ nx: p.nx!, ny: p.ny! }));
    // Вычисляем начальный масштаб из метрических данных модели
    let sum = 0, count = 0;
    for (let i = 0; i < raw.length; i++) {
      const j = (i + 1) % raw.length;
      const mdx = raw[j].x - raw[i].x;
      const mdy = raw[j].y - raw[i].y;
      const mLen = Math.sqrt(mdx * mdx + mdy * mdy);
      const pdx = (pts[j].nx - pts[i].nx) * SVG_W;
      const pdy = (pts[j].ny - pts[i].ny) * svgH;
      const pLen = Math.sqrt(pdx * pdx + pdy * pdy);
      if (pLen > 0 && mLen > 0) { sum += mLen / pLen; count++; }
    }
    return { points: pts, mPerPx: count > 0 ? sum / count : null };
  }

  // Fallback — нет nx/ny: раскладываем по bbox метрики
  const xs = raw.map((p) => p.x);
  const ys = raw.map((p) => p.y);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const rX = maxX - minX || 1, rY = maxY - minY || 1;
  const pad = 0.1;
  return {
    points: raw.map((p) => ({
      nx: pad + ((p.x - minX) / rX) * (1 - pad * 2),
      ny: pad + ((p.y - minY) / rY) * (1 - pad * 2),
    })),
    mPerPx: null,
  };
}

export default function BlueprintReview({ imageUrl, result, onApply, onCancel }: Props) {
  const [svgH, setSvgH] = useState(DEFAULT_SVG_H);
  const [points, setPoints] = useState<NormPoint[]>(() => computeGeometry(result, DEFAULT_SVG_H).points);
  const [mPerPx, setMPerPx] = useState<number | null>(() => computeGeometry(result, DEFAULT_SVG_H).mPerPx);
  const [draggingIdx, setDraggingIdx] = useState<number | null>(null);
  const userCalibrated = useRef(false);

  // Реальные пропорции фото узнаём только после загрузки — по умолчанию считаем 4:3,
  // как и раньше. Если пропорции другие, подгоняем высоту полотна и пересчитываем
  // масштаб (если пользователь ещё не откалибровал вручную — его выбор не трогаем).
  useEffect(() => {
    const img = new Image();
    img.onload = () => {
      if (img.naturalWidth > 0 && img.naturalHeight > 0) {
        setSvgH(Math.round(SVG_W * (img.naturalHeight / img.naturalWidth)));
      }
    };
    img.src = imageUrl;
  }, [imageUrl]);

  useEffect(() => {
    if (userCalibrated.current || svgH === DEFAULT_SVG_H) return;
    setMPerPx(computeGeometry(result, svgH).mPerPx);
  }, [svgH, result]);

  // Редактирование длины ребра
  const [editingEdge, setEditingEdge] = useState<number | null>(null);
  const [edgeInput, setEdgeInput] = useState("");

  // Калибровка
  const [calibMode, setCalibMode] = useState(false);
  const [calibPts, setCalibPts] = useState<NormPoint[]>([]);
  const [calibInput, setCalibInput] = useState("");

  const svgRef = useRef<SVGSVGElement>(null);

  const sx = (nx: number) => nx * SVG_W;
  const sy = (ny: number) => ny * svgH;
  const polygonStr = points.map((p) => `${sx(p.nx)},${sy(p.ny)}`).join(" ");

  const toNorm = (e: React.PointerEvent): NormPoint | null => {
    const svg = svgRef.current;
    if (!svg) return null;
    const ctm = svg.getScreenCTM();
    if (!ctm) return null;
    const pt = svg.createSVGPoint();
    pt.x = e.clientX;
    pt.y = e.clientY;
    const local = pt.matrixTransform(ctm.inverse());
    return {
      nx: Math.max(0, Math.min(1, local.x / SVG_W)),
      ny: Math.max(0, Math.min(1, local.y / svgH)),
    };
  };

  const snapToVertex = (norm: NormPoint): NormPoint => {
    for (const p of points) {
      const dx = (norm.nx - p.nx) * SVG_W;
      const dy = (norm.ny - p.ny) * svgH;
      if (Math.sqrt(dx * dx + dy * dy) <= 12) return { nx: p.nx, ny: p.ny };
    }
    return norm;
  };

  // Длина ребра в метрах — считается живо из nx/ny × mPerPx
  const edgeLenM = (a: NormPoint, b: NormPoint): number | null => {
    if (mPerPx === null) return null;
    const dx = (b.nx - a.nx) * SVG_W;
    const dy = (b.ny - a.ny) * svgH;
    return Math.sqrt(dx * dx + dy * dy) * mPerPx;
  };

  const formatLen = (len: number) => (len < 10 ? len.toFixed(2) : len.toFixed(1));

  // Drag вершины
  const handleVertexDown = (e: React.PointerEvent, idx: number) => {
    if (calibMode || editingEdge !== null) return;
    e.stopPropagation();
    setDraggingIdx(idx);
  };

  const handlePointerMove = (e: React.PointerEvent) => {
    if (draggingIdx === null) return;
    const norm = toNorm(e);
    if (!norm) return;
    setPoints((prev) => prev.map((p, i) => (i === draggingIdx ? norm : p)));
  };

  const handlePointerUp = () => setDraggingIdx(null);

  // Клик на SVG в режиме калибровки
  const handleSvgPointerDown = (e: React.PointerEvent) => {
    if (!calibMode) return;
    const raw = toNorm(e);
    if (!raw) return;
    const norm = snapToVertex(raw);
    const next = [...calibPts, norm];
    setCalibPts(next);
  };

  // Применить калибровку — сохраняем только mPerPx, не трогаем nx/ny
  const applyCalibration = () => {
    const dist = parseFloat(calibInput.replace(",", "."));
    if (isNaN(dist) || dist <= 0 || calibPts.length < 2) return;
    const [a, b] = calibPts;
    const dx = (b.nx - a.nx) * SVG_W;
    const dy = (b.ny - a.ny) * svgH;
    const pxDist = Math.sqrt(dx * dx + dy * dy);
    if (pxDist === 0) return;
    userCalibrated.current = true;
    setMPerPx(dist / pxDist);
    setCalibMode(false);
    setCalibPts([]);
    setCalibInput("");
  };

  // Ввод точной длины ребра — двигаем конечную вершину вдоль направления
  const submitEdge = (i: number) => {
    const newLen = parseFloat(edgeInput.replace(",", "."));
    setEditingEdge(null);
    setEdgeInput("");
    if (!mPerPx || isNaN(newLen) || newLen <= 0) return;
    const j = (i + 1) % points.length;
    const a = points[i], b = points[j];
    const dx = (b.nx - a.nx) * SVG_W;
    const dy = (b.ny - a.ny) * svgH;
    const curPx = Math.sqrt(dx * dx + dy * dy);
    if (curPx === 0) return;
    const scale = (newLen / mPerPx) / curPx;
    setPoints((prev) =>
      prev.map((p, idx) =>
        idx === j
          ? {
              nx: Math.max(0, Math.min(1, a.nx + (b.nx - a.nx) * scale)),
              ny: Math.max(0, Math.min(1, a.ny + (b.ny - a.ny) * scale)),
            }
          : p
      )
    );
  };

  // Применить — x/y считаем здесь, округляем до 2 знаков (точность ~1 см)
  const handleApply = () => {
    if (!mPerPx || points.length < 3) return;
    const origin = points[0];
    onApply(
      points.map((p) => ({
        x: Math.round(((p.nx - origin.nx) * SVG_W) * mPerPx * 100) / 100,
        y: Math.round(((p.ny - origin.ny) * svgH) * mPerPx * 100) / 100,
      })),
      result.height
    );
  };

  const isCalibrated = mPerPx !== null;

  const btnClass = (accent?: boolean, disabled?: boolean) =>
    [styles.btn, accent && !disabled && styles.btnAccent, disabled && styles.btnDisabled]
      .filter(Boolean)
      .join(" ");

  return (
    <div className={styles.wrapper}>
      <div className={styles.titleRow}>
        Проверка чертежа
        {!isCalibrated && (
          <span className={styles.calibWarning}>
            ⚠ нужна калибровка
          </span>
        )}
      </div>

      <div className={`${styles.canvasFrame} ${calibMode ? styles.canvasFrameCalib : ""}`}>
        <svg
          ref={svgRef}
          viewBox={`0 0 ${SVG_W} ${svgH}`}
          className={styles.svgRoot}
          onPointerDown={handleSvgPointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerLeave={handlePointerUp}
        >
          <image href={imageUrl} x={0} y={0} width={SVG_W} height={svgH}
            preserveAspectRatio="xMidYMid meet" />

          <polygon points={polygonStr} fill="rgba(176,123,94,0.15)"
            stroke="var(--accent)" strokeWidth="1.5" />

          {/* Подписи длин рёбер — живые, обновляются при drag */}
          {points.map((p, i) => {
            const next = points[(i + 1) % points.length];
            const len = edgeLenM(p, next);
            const midX = (sx(p.nx) + sx(next.nx)) / 2;
            const midY = (sy(p.ny) + sy(next.ny)) / 2;

            if (editingEdge === i) {
              return (
                <foreignObject key={`ei-${i}`} x={midX - 35} y={midY - 14} width="70" height="28"
                  className={styles.foreignObjectVisible}>
                  <input
                    autoFocus type="text" value={edgeInput}
                    onChange={(e) => setEdgeInput(e.target.value)}
                    onBlur={() => submitEdge(i)}
                    onClick={(e) => e.stopPropagation()}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") submitEdge(i);
                      if (e.key === "Escape") { setEditingEdge(null); setEdgeInput(""); }
                    }}
                    className={styles.edgeInput}
                  />
                </foreignObject>
              );
            }

            const label = len === null ? "?" : formatLen(len);
            return (
              <g key={`el-${i}`}
                className={isCalibrated && !calibMode ? styles.edgeLabelGroupActive : styles.edgeLabelGroup}
                onClick={() => {
                  if (!isCalibrated || calibMode || draggingIdx !== null) return;
                  setEditingEdge(i);
                  setEdgeInput(len !== null ? formatLen(len) : "");
                }}>
                <rect x={midX - 18} y={midY - 9} width="36" height="16" rx="2"
                  fill="rgba(0,0,0,0.6)" />
                <text x={midX} y={midY + 1} fill={len === null ? "#888" : "#fff"}
                  fontSize="9" textAnchor="middle" dominantBaseline="middle">
                  {label}{len !== null ? "м" : ""}
                </text>
              </g>
            );
          })}

          {/* Вершины */}
          {points.map((p, i) => {
            const snapped = calibPts.some((cp) => cp.nx === p.nx && cp.ny === p.ny);
            return (
              <circle key={i} cx={sx(p.nx)} cy={sy(p.ny)}
                r={draggingIdx === i ? 7 : calibMode ? 7 : 5}
                fill={snapped ? "#4caf50" : draggingIdx === i ? "var(--accent)" : "#fff"}
                stroke={snapped ? "#4caf50" : "var(--accent)"}
                strokeWidth="1.5"
                className={calibMode ? styles.vertexCircleCalib : styles.vertexCircle}
                onPointerDown={(e) => handleVertexDown(e, i)} />
            );
          })}

          {/* Калибровочные точки */}
          {calibPts.map((cp, i) => (
            <circle key={`cp-${i}`} cx={sx(cp.nx)} cy={sy(cp.ny)} r={5}
              fill="#4caf50" stroke="#fff" strokeWidth="1.5" />
          ))}
          {calibPts.length === 2 && (
            <line x1={sx(calibPts[0].nx)} y1={sy(calibPts[0].ny)}
              x2={sx(calibPts[1].nx)} y2={sy(calibPts[1].ny)}
              stroke="#4caf50" strokeWidth="1" strokeDasharray="4 3" />
          )}
        </svg>
      </div>

      {/* Панель калибровки */}
      {calibMode && (
        <div className={styles.calibPanel}>
          {calibPts.length === 0 && "Кликните на первую вершину"}
          {calibPts.length === 1 && "Кликните на вторую вершину"}
          {calibPts.length === 2 && (
            <div className={styles.calibDistanceRow}>
              <span>Расстояние (м):</span>
              <input autoFocus type="text" value={calibInput}
                onChange={(e) => setCalibInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && applyCalibration()}
                className={styles.calibInput} />
              <button onClick={applyCalibration} className={btnClass()}>OK</button>
              <button onClick={() => { setCalibMode(false); setCalibPts([]); setCalibInput(""); }}
                className={btnClass()}>Отмена</button>
            </div>
          )}
        </div>
      )}

      <div className={styles.controlsRow}>
        {!calibMode && (
          <button onClick={() => { setCalibMode(true); setCalibPts([]); }} className={btnClass()}>
            {isCalibrated ? "Перекалибровать" : "Калибровка масштаба"}
          </button>
        )}
        <button onClick={handleApply} disabled={!isCalibrated || points.length < 3}
          className={`${btnClass(true, !isCalibrated || points.length < 3)} ${styles.btnApply}`}>
          Применить
        </button>
        <button onClick={onCancel} className={btnClass()}>Отмена</button>
      </div>

      <p className={styles.footerHint}>
        {isCalibrated
          ? "Тащи вершины · кликай на подпись ребра для точного ввода длины"
          : "Сначала откалибруй — кликни на две вершины и введи реальное расстояние"}
      </p>
    </div>
  );
}
