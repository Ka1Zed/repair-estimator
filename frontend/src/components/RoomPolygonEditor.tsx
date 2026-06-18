import { useState, useRef } from "react";
import { useProjectStore } from "../store/projectStore";

export default function RoomPolygonEditor() {
  const points = useProjectStore((state) => state.points);
  const updatePoint = useProjectStore((state) => state.updatePoint);
  const setPoints = useProjectStore((state) => state.setPoints);

  const [draggingIdx, setDraggingIdx] = useState<number | null>(null);

  // НОВЫЙ СТЕЙТ: включена ли привязка к сетке (по умолчанию да)
  const [snapToGrid, setSnapToGrid] = useState(true);

  const svgRef = useRef<SVGSVGElement>(null);

  if (points.length < 3) {
    return (
      <div style={{ color: "#888", marginTop: "20px" }}>
        Добавьте минимум 3 точки для отображения плана
      </div>
    );
  }

  const safePoints = points.map((p) => ({
    x: Number(p.x) || 0,
    y: Number(p.y) || 0,
  }));

  const xs = safePoints.map((p) => p.x);
  const ys = safePoints.map((p) => p.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);

  const rangeX = maxX - minX;
  const rangeY = maxY - minY;
  const effectiveRangeX = rangeX === 0 ? 1 : rangeX;
  const effectiveRangeY = rangeY === 0 ? 1 : rangeY;

  const MAX_PREVIEW_WIDTH = 400;
  const MAX_PREVIEW_HEIGHT = 300;

  const paddingX = effectiveRangeX * 0.1;
  const paddingY = effectiveRangeY * 0.1;
  const totalViewWidth = effectiveRangeX + paddingX * 2;
  const totalViewHeight = effectiveRangeY + paddingY * 2;

  const scaleX = MAX_PREVIEW_WIDTH / totalViewWidth;
  const scaleY = MAX_PREVIEW_HEIGHT / totalViewHeight;
  const scale = Math.min(scaleX, scaleY);

  const svgWidth = totalViewWidth * scale;
  const svgHeight = totalViewHeight * scale;
  const offsetX = minX - paddingX;
  const offsetY = minY - paddingY;

  // --- ЛОГИКА УМНОЙ СЕТКИ ---
  const GRID_STEP = 0.5; // Шаг сетки 0.5 метра
  const gridPixelSize = GRID_STEP * scale; // Размер одной клетки в пикселях на экране

  // Смещение сетки, чтобы линии четко попадали в целые координаты (0, 0.5, 1 и т.д.)
  const gridOffsetX = (-offsetX * scale) % gridPixelSize;
  const gridOffsetY = (-offsetY * scale) % gridPixelSize;

  const pointsString = safePoints
    .map((p) => `${(p.x - offsetX) * scale},${(p.y - offsetY) * scale}`)
    .join(" ");

  const handlePointerDown = (index: number) => {
    setDraggingIdx(index);
  };

  const handlePointerMove = (e: React.PointerEvent) => {
    if (draggingIdx === null || !svgRef.current) return;

    const svg = svgRef.current;
    const ctm = svg.getScreenCTM();
    if (!ctm) return;

    const pt = svg.createSVGPoint();
    pt.x = e.clientX;
    pt.y = e.clientY;
    const cursorPt = pt.matrixTransform(ctm.inverse());

    let newRealX = cursorPt.x / scale + offsetX;
    let newRealY = cursorPt.y / scale + offsetY;

    // --- МАГНИТ К СЕТКЕ ---
    if (snapToGrid) {
      newRealX = Math.round(newRealX / GRID_STEP) * GRID_STEP;
      newRealY = Math.round(newRealY / GRID_STEP) * GRID_STEP;
    }

    newRealX = Math.max(0, Math.round(newRealX * 10) / 10);
    newRealY = Math.max(0, Math.round(newRealY * 10) / 10);

    updatePoint(draggingIdx, newRealX, newRealY);
  };

  const handlePointerUp = () => {
    setDraggingIdx(null);
  };

  const handleDeletePoint = (index: number, e: React.PointerEvent) => {
    if (e.shiftKey) {
      if (points.length <= 3) {
        alert("У помещения должно быть минимум 3 точки!");
        return;
      }
      setPoints(points.filter((_, i) => i !== index));
    } else {
      handlePointerDown(index);
    }
  };

  const handleEdgeClick = (e: React.PointerEvent, index1: number) => {
    const svg = svgRef.current;
    if (!svg) return;
    const ctm = svg.getScreenCTM();
    if (!ctm) return;

    const pt = svg.createSVGPoint();
    pt.x = e.clientX;
    pt.y = e.clientY;
    const cursorPt = pt.matrixTransform(ctm.inverse());

    let newRealX = cursorPt.x / scale + offsetX;
    let newRealY = cursorPt.y / scale + offsetY;

    // --- МАГНИТ ПРИ ДОБАВЛЕНИИ ТОЧКИ ---
    if (snapToGrid) {
      newRealX = Math.round(newRealX / GRID_STEP) * GRID_STEP;
      newRealY = Math.round(newRealY / GRID_STEP) * GRID_STEP;
    }

    newRealX = Math.max(0, Math.round(newRealX * 10) / 10);
    newRealY = Math.max(0, Math.round(newRealY * 10) / 10);

    const newPoints = [...points];
    newPoints.splice(index1 + 1, 0, { x: newRealX, y: newRealY });
    setPoints(newPoints);
  };

  return (
    <div style={{ marginTop: "20px", width: "100%", maxWidth: "450px" }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-end",
          marginBottom: "10px",
        }}
      >
        <div>
          <h3>Редактор помещения:</h3>
          <p
            style={{
              fontSize: "13px",
              color: "#888",
              margin: 0,
              marginTop: "5px",
            }}
          >
            💡 Клик по границе — добавить точку.
            <br />
            💡 <b>Shift + Клик</b> по точке — удалить.
          </p>
        </div>

        {/* ТУМБЛЕР ПРИВЯЗКИ */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "flex-end",
          }}
        >
          <label
            style={{
              display: "flex",
              alignItems: "center",
              cursor: "pointer",
              fontSize: "14px",
              color: "#ddd",
            }}
          >
            <input
              type="checkbox"
              checked={snapToGrid}
              onChange={(e) => setSnapToGrid(e.target.checked)}
              style={{ marginRight: "6px" }}
            />
            Привязка к узлам
          </label>
          <span style={{ fontSize: "11px", color: "#666", marginTop: "4px" }}>
            1 клетка = 0.5 м
          </span>
        </div>
      </div>

      <div
        style={{
          background: "#222",
          padding: "20px",
          borderRadius: "8px",
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          boxSizing: "border-box",
          minHeight: "150px",
          cursor: draggingIdx !== null ? "grabbing" : "default",
        }}
      >
        <svg
          ref={svgRef}
          viewBox={`0 0 ${svgWidth} ${svgHeight}`}
          style={{
            display: "block",
            touchAction: "none",
            width: "100%",
            height: "auto",
            maxHeight: "300px",
            overflow: "visible",
          }}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerLeave={handlePointerUp}
        >
          <defs>
            {/* Отрисовка самой сетки с привязкой координат */}
            <pattern
              id="grid"
              width={gridPixelSize}
              height={gridPixelSize}
              patternUnits="userSpaceOnUse"
              patternTransform={`translate(${gridOffsetX}, ${gridOffsetY})`}
            >
              <path
                d={`M ${gridPixelSize} 0 L 0 0 0 ${gridPixelSize}`}
                fill="none"
                stroke="#333"
                strokeWidth="1"
              />
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#grid)" />

          <polygon
            points={pointsString}
            fill="rgba(100, 200, 100, 0.3)"
            stroke="#5cba5c"
            strokeWidth="3"
          />

          {safePoints.map((p, i) => {
            const nextIndex = (i + 1) % safePoints.length;
            const nextP = safePoints[nextIndex];
            return (
              <line
                key={`edge-${i}`}
                x1={(p.x - offsetX) * scale}
                y1={(p.y - offsetY) * scale}
                x2={(nextP.x - offsetX) * scale}
                y2={(nextP.y - offsetY) * scale}
                stroke="transparent"
                strokeWidth="15"
                style={{ cursor: "crosshair" }}
                onPointerDown={(e) => handleEdgeClick(e, i)}
              />
            );
          })}

          {safePoints.map((p, i) => (
            <circle
              key={i}
              cx={(p.x - offsetX) * scale}
              cy={(p.y - offsetY) * scale}
              r={draggingIdx === i ? "8" : "6"}
              fill={draggingIdx === i ? "#5cba5c" : "#fff"}
              stroke="#5cba5c"
              strokeWidth="2"
              onPointerDown={(e) => handleDeletePoint(i, e)}
              style={{ cursor: "grab" }}
            />
          ))}
        </svg>
      </div>
    </div>
  );
}
