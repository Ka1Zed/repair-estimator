import { useState, useRef, useMemo, useEffect, useLayoutEffect } from "react";
import { useProjectStore } from "../store/projectStore";
import { getSelfIntersectingEdges } from "../utils/polygonValidation";
import styles from "./RoomPolygonEditor.module.css";

type ViewBox = { x: number; y: number; w: number; h: number };

const GRID_STEP = 0.5; // metres

export default function RoomPolygonEditor() {
  const activeRoomIndex = useProjectStore((state) => state.activeRoomIndex);
  const points = useProjectStore((state) => state.rooms[activeRoomIndex].points);
  const updatePoint = useProjectStore((state) => state.updatePoint);
  const setPoints = useProjectStore((state) => state.setPoints);
  const clearActiveRoom = useProjectStore((state) => state.clearActiveRoom);
  const loadDemoRoom = useProjectStore((state) => state.loadDemoRoom);
  const resetProject = useProjectStore((state) => state.resetProject);

  const [draggingIdx, setDraggingIdx] = useState<number | null>(null);
  const [snapToGrid, setSnapToGrid] = useState(true);
  // Транзиентное сообщение вместо блокирующего alert (напр. попытка удалить
  // точку, когда их уже минимум 3) — гасим само через несколько секунд.
  const [pointCountError, setPointCountError] = useState<string | null>(null);
  const [editingEdge, setEditingEdge] = useState<number | null>(null);
  const [edgeInputValue, setEdgeInputValue] = useState("");

  // null = auto-fit, non-null = user has zoomed/panned
  const [userViewBox, setUserViewBox] = useState<ViewBox | null>(null);
  // frozen viewBox during vertex drag to prevent coordinate feedback loop
  const [dragVb, setDragVb] = useState<ViewBox | null>(null);
  const [isPanning, setIsPanning] = useState(false);

  const svgRef = useRef<SVGSVGElement>(null);
  // pan state stored in ref (only read inside event handlers, not during render)
  const panRef = useRef<{ startX: number; startY: number; vb: ViewBox; ctm: DOMMatrix } | null>(null);

  const safePoints = useMemo(
    () => points.map((p) => ({ x: Number(p.x) || 0, y: Number(p.y) || 0 })),
    [points],
  );

  const autoViewBox = useMemo((): ViewBox => {
    if (safePoints.length < 3) return { x: -1, y: -1, w: 10, h: 8 };
    const xs = safePoints.map((p) => p.x);
    const ys = safePoints.map((p) => p.y);
    const minX = Math.min(...xs), maxX = Math.max(...xs);
    const minY = Math.min(...ys), maxY = Math.max(...ys);
    const pw = Math.max(maxX - minX, 0.1);
    const ph = Math.max(maxY - minY, 0.1);
    const pad = Math.max(pw, ph) * 0.18;
    return { x: minX - pad, y: minY - pad, w: pw + pad * 2, h: ph + pad * 2 };
  }, [safePoints]);

  // During vertex drag freeze viewBox so CTM stays stable
  const vb: ViewBox = (draggingIdx !== null && dragVb) ? dragVb : (userViewBox ?? autoViewBox);

  // Ref for wheel handler — keeps listener stable (no re-add on every pan/drag frame)
  const vbRef = useRef<ViewBox>(vb);
  useLayoutEffect(() => { vbRef.current = vb; });

  const viewBoxStr = `${vb.x} ${vb.y} ${vb.w} ${vb.h}`;

  // Scale-invariant sizes (proportional to viewBox width)
  const pointR = vb.w * 0.018;
  const fontSize = vb.w * 0.032;
  const labelW = vb.w * 0.12;
  const labelH = vb.w * 0.052;

  const badEdges = useMemo(() => getSelfIntersectingEdges(points), [points]);
  const hasBadEdges = badEdges.size > 0;

  // Convert screen pixel coords to SVG user (real) coords using current CTM
  const screenToReal = (clientX: number, clientY: number, ctm?: DOMMatrix) => {
    const svg = svgRef.current;
    if (!svg) return { x: 0, y: 0 };
    const resolvedCtm = ctm ?? svg.getScreenCTM();
    if (!resolvedCtm) return { x: 0, y: 0 };
    const pt = svg.createSVGPoint();
    pt.x = clientX;
    pt.y = clientY;
    return pt.matrixTransform(resolvedCtm.inverse());
  };

  const calculateDistance = (p1: { x: number; y: number }, p2: { x: number; y: number }) =>
    Math.sqrt((p2.x - p1.x) ** 2 + (p2.y - p1.y) ** 2);

  // --- Vertex drag ---
  const handlePointerDown = (index: number) => {
    setDragVb(userViewBox ?? autoViewBox);
    setDraggingIdx(index);
    setEditingEdge(null);
  };

  const handlePointerMove = (e: React.PointerEvent) => {
    if (draggingIdx === null) return;
    let { x, y } = screenToReal(e.clientX, e.clientY);
    if (snapToGrid) {
      x = Math.round(x / GRID_STEP) * GRID_STEP;
      y = Math.round(y / GRID_STEP) * GRID_STEP;
    } else {
      x = Math.round(x * 1000) / 1000;
      y = Math.round(y * 1000) / 1000;
    }
    updatePoint(draggingIdx, x, y);
  };

  const handlePointerUp = () => {
    setDragVb(null);
    setDraggingIdx(null);
  };

  const handleDeletePoint = (index: number, e: React.PointerEvent) => {
    if (e.shiftKey) {
      if (points.length <= 3) {
        setPointCountError("У комнаты должно быть минимум 3 точки.");
        setTimeout(() => setPointCountError(null), 4000);
        return;
      }
      setPointCountError(null);
      setPoints(points.filter((_, i) => i !== index));
    } else {
      handlePointerDown(index);
    }
  };

  // --- Add point on edge click ---
  const handleEdgeClick = (e: React.PointerEvent, index1: number) => {
    if (editingEdge !== null) return;
    let { x, y } = screenToReal(e.clientX, e.clientY);
    if (snapToGrid) {
      x = Math.round(x / GRID_STEP) * GRID_STEP;
      y = Math.round(y / GRID_STEP) * GRID_STEP;
    } else {
      x = Math.round(x * 1000) / 1000;
      y = Math.round(y * 1000) / 1000;
    }
    const newPoints = [...points];
    newPoints.splice(index1 + 1, 0, { x, y });
    setPoints(newPoints);
  };

  // --- Edge length edit ---
  const handleEdgeLengthSubmit = (index: number) => {
    if (!edgeInputValue) { setEditingEdge(null); return; }
    const newLen = parseFloat(edgeInputValue.replace(",", "."));
    if (isNaN(newLen) || newLen <= 0) { setEditingEdge(null); return; }
    const p1 = safePoints[index];
    const nextIndex = (index + 1) % safePoints.length;
    const p2 = safePoints[nextIndex];
    const currentLen = calculateDistance(p1, p2);
    if (currentLen === 0) { setEditingEdge(null); return; }
    const nx = (p2.x - p1.x) / currentLen;
    const ny = (p2.y - p1.y) / currentLen;
    let newX = p1.x + nx * newLen;
    let newY = p1.y + ny * newLen;
    if (snapToGrid) {
      newX = Math.round(newX / GRID_STEP) * GRID_STEP;
      newY = Math.round(newY / GRID_STEP) * GRID_STEP;
    } else {
      newX = Math.round(newX * 1000) / 1000;
      newY = Math.round(newY * 1000) / 1000;
    }
    updatePoint(nextIndex, newX, newY);
    setEditingEdge(null);
    setEdgeInputValue("");
  };

  // --- Pan ---
  const handleBgDown = (e: React.PointerEvent) => {
    if (draggingIdx !== null || editingEdge !== null) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    const svg = svgRef.current;
    if (!svg) return;
    const ctm = svg.getScreenCTM();
    if (!ctm) return;
    const { x, y } = screenToReal(e.clientX, e.clientY, ctm);
    panRef.current = { startX: x, startY: y, vb: userViewBox ?? autoViewBox, ctm };
    setIsPanning(true);
  };

  const handleBgMove = (e: React.PointerEvent) => {
    if (!panRef.current) return;
    const current = screenToReal(e.clientX, e.clientY, panRef.current.ctm);
    const dx = current.x - panRef.current.startX;
    const dy = current.y - panRef.current.startY;
    const pv = panRef.current.vb;
    setUserViewBox({ x: pv.x - dx, y: pv.y - dy, w: pv.w, h: pv.h });
  };

  const handleBgUp = () => {
    panRef.current = null;
    setIsPanning(false);
  };

  // --- Zoom (нативный listener — React вешает onWheel пассивно, поэтому
  //     preventDefault() в нём no-op и страница скроллится вместе с зумом)
  //     Читаем vbRef.current вместо замыкания на state — listener стабилен,
  //     не пересоздаётся на каждый pointermove при пане/драге. ---
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const cursor = screenToReal(e.clientX, e.clientY);
      const cv = vbRef.current;
      // Math.pow учитывает величину deltaY → плавный зум на трекпаде
      const factor = Math.pow(1.0015, e.deltaY);
      const newW = Math.min(Math.max(cv.w * factor, 0.5), 500);
      const newH = cv.h * (newW / cv.w);
      const rx = (cursor.x - cv.x) / cv.w;
      const ry = (cursor.y - cv.y) / cv.h;
      setUserViewBox({ x: cursor.x - rx * newW, y: cursor.y - ry * newH, w: newW, h: newH });
    };
    svg.addEventListener("wheel", onWheel, { passive: false });
    return () => svg.removeEventListener("wheel", onWheel);
  }, []);

  // --- Fit to view ---
  const handleFitToView = () => setUserViewBox(null);

  const pointsStr = safePoints.map((p) => `${p.x},${p.y}`).join(" ");

  const controlButtonsJSX = (
    <div className={styles.controlsRow}>
      <button onClick={resetProject} className={styles.btnReset}>
        Сбросить черновик
      </button>
      <button onClick={clearActiveRoom} className={styles.btnClear}>
        Очистить комнату
      </button>
      <button onClick={loadDemoRoom} className={styles.btnDemo}>
        Загрузить пример
      </button>
    </div>
  );

  if (points.length < 3) {
    return (
      <div className={styles.emptyWrap}>
        <div className={styles.emptyHint}>
          Добавьте минимум 3 точки для отображения плана или загрузите готовый пример.
        </div>
        {controlButtonsJSX}
      </div>
    );
  }

  return (
    <div className={styles.canvasWrap}>
      <div className={styles.headerRow}>
        <p className={styles.hintText}>
          💡 Клик по границе — добавить точку.
          <br />
          💡 <b>Клик по ценнику</b> — задать точную длину.
          <br />
          💡 <b>Shift + Клик</b> по точке — удалить.
        </p>
        <div className={styles.rightControls}>
          <label className={styles.snapLabel}>
            <input type="checkbox" checked={snapToGrid} onChange={(e) => setSnapToGrid(e.target.checked)} className={styles.snapCheckbox} />
            Привязка к узлам
          </label>
          <span className={styles.gridLegend}>1 клетка = 0.5 м</span>
          {userViewBox && (
            <button onClick={handleFitToView} className={styles.btnFit}>
              Вписать
            </button>
          )}
        </div>
      </div>

      <div
        className={`${styles.canvasFrame} ${isPanning || draggingIdx !== null ? styles.canvasFrameGrabbing : ""}`}
      >
        <svg
          ref={svgRef}
          viewBox={viewBoxStr}
          width="100%"
          height="100%"
          preserveAspectRatio="xMidYMid meet"
          className={styles.svgRoot}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerLeave={handlePointerUp}
        >
          <defs>
            <pattern id="rpeg-grid" width={GRID_STEP} height={GRID_STEP} patternUnits="userSpaceOnUse">
              <circle cx={GRID_STEP / 2} cy={GRID_STEP / 2} r={GRID_STEP * 0.06} fill="#DDDDDD" />
            </pattern>
          </defs>

          {/* background: covers full viewBox */}
          <rect
            x={vb.x - vb.w}
            y={vb.y - vb.h}
            width={vb.w * 3}
            height={vb.h * 3}
            fill="white"
            onPointerDown={handleBgDown}
            onPointerMove={handleBgMove}
            onPointerUp={handleBgUp}
            onPointerCancel={handleBgUp}
          />
          <rect
            x={vb.x - vb.w}
            y={vb.y - vb.h}
            width={vb.w * 3}
            height={vb.h * 3}
            fill="url(#rpeg-grid)"
            className={styles.noPointerEvents}
          />

          {/* polygon fill */}
          <polygon
            points={pointsStr}
            fill={hasBadEdges ? "rgba(176,70,70,0.05)" : "rgba(176,123,94,0.06)"}
            stroke="none"
            className={styles.noPointerEvents}
          />

          {/* edge stroke */}
          {safePoints.map((p, i) => {
            const np = safePoints[(i + 1) % safePoints.length];
            const isBad = badEdges.has(i);
            return (
              <line
                key={`es-${i}`}
                x1={p.x} y1={p.y} x2={np.x} y2={np.y}
                stroke={isBad ? "var(--error)" : "var(--accent)"}
                strokeWidth={isBad ? vb.w * 0.006 : vb.w * 0.004}
                strokeDasharray={isBad ? `${vb.w * 0.015} ${vb.w * 0.009}` : undefined}
                className={styles.noPointerEvents}
              />
            );
          })}

          {/* edge hit targets */}
          {safePoints.map((p, i) => {
            const np = safePoints[(i + 1) % safePoints.length];
            return (
              <line
                key={`eh-${i}`}
                x1={p.x} y1={p.y} x2={np.x} y2={np.y}
                stroke="transparent"
                strokeWidth={vb.w * 0.05}
                className={styles.edgeHitTarget}
                onPointerDown={(e) => handleEdgeClick(e, i)}
              />
            );
          })}

          {/* edge labels */}
          {safePoints.map((p, i) => {
            const np = safePoints[(i + 1) % safePoints.length];
            const mx = (p.x + np.x) / 2;
            const my = (p.y + np.y) / 2;
            const len = calculateDistance(p, np);
            const displayLen = Number.isInteger(len) ? len.toString() : len.toFixed(1);

            if (editingEdge === i) {
              return (
                <foreignObject key={`ei-${i}`} x={mx - labelW / 2} y={my - labelH / 2} width={labelW} height={labelH} className={styles.foreignObjectVisible}>
                  <input
                    autoFocus
                    type="text"
                    value={edgeInputValue}
                    onChange={(e) => setEdgeInputValue(e.target.value)}
                    onBlur={() => handleEdgeLengthSubmit(i)}
                    onClick={(e) => e.stopPropagation()}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") handleEdgeLengthSubmit(i);
                      if (e.key === "Escape") { setEdgeInputValue(""); setEditingEdge(null); }
                    }}
                    className={styles.edgeInput}
                    style={{
                      fontSize,
                      borderWidth: vb.w * 0.003,
                      borderRadius: vb.w * 0.008,
                    }}
                  />
                </foreignObject>
              );
            }

            return (
              <g
                key={`el-${i}`}
                className={styles.edgeLabelGroup}
                onClick={(e) => { e.stopPropagation(); setEditingEdge(i); setEdgeInputValue(displayLen); }}
              >
                <rect x={mx - labelW / 2} y={my - labelH / 2} width={labelW} height={labelH} rx={vb.w * 0.008} fill="#FFFFFF" stroke="var(--border)" strokeWidth={vb.w * 0.003} />
                <text x={mx} y={my} fill="#6B6B6B" fontSize={fontSize} textAnchor="middle" dominantBaseline="central" className={styles.edgeLabelText}>
                  {displayLen}м
                </text>
              </g>
            );
          })}

          {/* vertex circles */}
          {safePoints.map((p, i) => (
            <circle
              key={`v-${i}`}
              cx={p.x} cy={p.y}
              r={draggingIdx === i ? pointR * 1.3 : pointR}
              fill={draggingIdx === i ? "var(--accent)" : "#FFFFFF"}
              stroke="var(--accent)"
              strokeWidth={vb.w * 0.003}
              onPointerDown={(e) => handleDeletePoint(i, e)}
              className={styles.vertexCircle}
            />
          ))}
        </svg>
      </div>

      {hasBadEdges && (
        <div className={styles.errorBox}>
          Контур самопересекается — площадь будет неверной. Исправьте форму комнаты.
        </div>
      )}

      {pointCountError && <div className={styles.errorBox}>{pointCountError}</div>}

      {controlButtonsJSX}
    </div>
  );
}
