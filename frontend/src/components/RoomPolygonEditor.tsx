import { useState, useRef } from "react";
import { useProjectStore } from "../store/projectStore";

export default function RoomPolygonEditor() {
  const activeRoomIndex = useProjectStore((state) => state.activeRoomIndex);
  const points = useProjectStore(
    (state) => state.rooms[activeRoomIndex].points,
  );
  const updatePoint = useProjectStore((state) => state.updatePoint);
  const setPoints = useProjectStore((state) => state.setPoints);

  const clearActiveRoom = useProjectStore((state) => state.clearActiveRoom);
  const loadDemoRoom = useProjectStore((state) => state.loadDemoRoom);
  const resetProject = useProjectStore((state) => state.resetProject);

  const [draggingIdx, setDraggingIdx] = useState<number | null>(null);
  const [snapToGrid, setSnapToGrid] = useState(true);

  const [editingEdge, setEditingEdge] = useState<number | null>(null);
  const [edgeInputValue, setEdgeInputValue] = useState("");

  const svgRef = useRef<SVGSVGElement>(null);

  const controlButtonsJSX = (
    <div
      style={{
        display: "flex",
        gap: "10px",
        marginTop: "15px",
        justifyContent: "flex-end",
        flexWrap: "wrap",
      }}
    >
      <button
        onClick={resetProject}
        style={{
          padding: "8px 12px",
          background: "#c0392b",
          color: "#fff",
          border: "none",
          borderRadius: "4px",
          cursor: "pointer",
          fontSize: "14px",
          marginRight: "auto",
        }}
      >
        Сбросить черновик
      </button>
      <button
        onClick={clearActiveRoom}
        style={{
          padding: "8px 12px",
          background: "transparent",
          color: "#e74c3c",
          border: "1px solid #e74c3c",
          borderRadius: "4px",
          cursor: "pointer",
          fontSize: "14px",
        }}
      >
        Очистить комнату
      </button>
      <button
        onClick={loadDemoRoom}
        style={{
          padding: "8px 12px",
          background: "#3498db",
          color: "#fff",
          border: "none",
          borderRadius: "4px",
          cursor: "pointer",
          fontSize: "14px",
        }}
      >
        Загрузить пример
      </button>
    </div>
  );

  if (points.length < 3) {
    return (
      <div style={{ marginTop: "20px", width: "100%", maxWidth: "450px" }}>
        <div style={{ color: "#888", marginBottom: "15px" }}>
          Добавьте минимум 3 точки для отображения плана или загрузите готовый
          пример.
        </div>
        {controlButtonsJSX}
      </div>
    );
  }

  const safePoints = points.map((p) => ({
    x: Number(p.x) || 0,
    y: Number(p.y) || 0,
  }));

  const calculateDistance = (
    p1: { x: number; y: number },
    p2: { x: number; y: number },
  ) => {
    return Math.sqrt(Math.pow(p2.x - p1.x, 2) + Math.pow(p2.y - p1.y, 2));
  };

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

  const paddingX = effectiveRangeX * 0.2;
  const paddingY = effectiveRangeY * 0.2;
  const totalViewWidth = effectiveRangeX + paddingX * 2;
  const totalViewHeight = effectiveRangeY + paddingY * 2;

  const scaleX = MAX_PREVIEW_WIDTH / totalViewWidth;
  const scaleY = MAX_PREVIEW_HEIGHT / totalViewHeight;
  const scale = Math.min(scaleX, scaleY);

  const svgWidth = totalViewWidth * scale;
  const svgHeight = totalViewHeight * scale;
  const offsetX = minX - paddingX;
  const offsetY = minY - paddingY;

  const GRID_STEP = 0.5;
  const gridPixelSize = GRID_STEP * scale;

  const gridOffsetX = (-offsetX * scale) % gridPixelSize;
  const gridOffsetY = (-offsetY * scale) % gridPixelSize;

  const pointsString = safePoints
    .map((p) => `${(p.x - offsetX) * scale},${(p.y - offsetY) * scale}`)
    .join(" ");

  const handlePointerDown = (index: number) => {
    setDraggingIdx(index);
    setEditingEdge(null);
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

    if (snapToGrid) {
      newRealX = Math.round(newRealX / GRID_STEP) * GRID_STEP;
      newRealY = Math.round(newRealY / GRID_STEP) * GRID_STEP;
    } else {
      newRealX = Math.round(newRealX * 1000) / 1000;
      newRealY = Math.round(newRealY * 1000) / 1000;
    }

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
    if (editingEdge !== null) return;

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

    if (snapToGrid) {
      newRealX = Math.round(newRealX / GRID_STEP) * GRID_STEP;
      newRealY = Math.round(newRealY / GRID_STEP) * GRID_STEP;
    } else {
      newRealX = Math.round(newRealX * 1000) / 1000;
      newRealY = Math.round(newRealY * 1000) / 1000;
    }

    const newPoints = [...points];
    newPoints.splice(index1 + 1, 0, { x: newRealX, y: newRealY });
    setPoints(newPoints);
  };

  const handleEdgeLengthSubmit = (index: number) => {
    if (!edgeInputValue) {
      setEditingEdge(null);
      return;
    }

    const newLen = parseFloat(edgeInputValue.replace(",", "."));
    if (isNaN(newLen) || newLen <= 0) {
      setEditingEdge(null);
      return;
    }

    const p1 = safePoints[index];
    const nextIndex = (index + 1) % safePoints.length;
    const p2 = safePoints[nextIndex];

    const currentLen = calculateDistance(p1, p2);
    if (currentLen === 0) {
      setEditingEdge(null);
      return;
    }

    const dx = p2.x - p1.x;
    const dy = p2.y - p1.y;

    const nx = dx / currentLen;
    const ny = dy / currentLen;

    let newRealX = p1.x + nx * newLen;
    let newRealY = p1.y + ny * newLen;

    newRealX = Math.round(newRealX * 1000) / 1000;
    newRealY = Math.round(newRealY * 1000) / 1000;

    updatePoint(nextIndex, newRealX, newRealY);
    setEditingEdge(null);
    setEdgeInputValue("");
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
          <div
            style={{
              fontSize: "11px",
              letterSpacing: ".16em",
              textTransform: "uppercase",
              color: "#B0B0B0",
              marginBottom: "8px",
            }}
          >
            Проект · план помещения
          </div>
          <p
            style={{
              fontSize: "13px",
              color: "#8A8A8A",
              margin: 0,
            }}
          >
            💡 Клик по границе — добавить точку.
            <br />
            💡 <b>Клик по ценнику</b> — задать точную длину.
            <br />
            💡 <b>Shift + Клик</b> по точке — удалить.
          </p>
        </div>

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
              fontSize: "12px",
              color: "#8A8A8A",
            }}
          >
            <input
              type="checkbox"
              checked={snapToGrid}
              onChange={(e) => setSnapToGrid(e.target.checked)}
              style={{ marginRight: "6px", accentColor: "var(--accent)" }}
            />
            Привязка к узлам
          </label>
          <span style={{ fontSize: "11px", color: "#B8B8B8", marginTop: "4px" }}>
            1 клетка = 0.5 м
          </span>
        </div>
      </div>

      <div
        style={{
          background: "var(--bg-canvas)",
          border: "1px solid var(--border)",
          padding: "20px",
          borderRadius: "4px",
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
            <pattern
              id="grid"
              width={gridPixelSize}
              height={gridPixelSize}
              patternUnits="userSpaceOnUse"
              patternTransform={`translate(${gridOffsetX}, ${gridOffsetY})`}
            >
              <circle
                cx={gridPixelSize / 2}
                cy={gridPixelSize / 2}
                r="1"
                fill="#DDDDDD"
              />
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="#FFFFFF" />
          <rect width="100%" height="100%" fill="url(#grid)" />

          <polygon
            points={pointsString}
            fill="rgba(176,123,94,0.06)"
            stroke="var(--accent)"
            strokeWidth="1.5"
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

          {safePoints.map((p, i) => {
            const nextIndex = (i + 1) % safePoints.length;
            const nextP = safePoints[nextIndex];

            const midX = (p.x + nextP.x) / 2;
            const midY = (p.y + nextP.y) / 2;

            const screenMidX = (midX - offsetX) * scale;
            const screenMidY = (midY - offsetY) * scale;

            const currentLen = calculateDistance(p, nextP);
            const displayLen = Number.isInteger(currentLen)
              ? currentLen.toString()
              : currentLen.toFixed(1);

            if (editingEdge === i) {
              return (
                <foreignObject
                  key={`edge-input-${i}`}
                  x={screenMidX - 35}
                  y={screenMidY - 15}
                  width="70"
                  height="30"
                  style={{ overflow: "visible" }}
                >
                  <input
                    autoFocus
                    type="text"
                    value={edgeInputValue}
                    onChange={(e) => setEdgeInputValue(e.target.value)}
                    onBlur={() => handleEdgeLengthSubmit(i)}
                    onClick={(e) => e.stopPropagation()}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") handleEdgeLengthSubmit(i);
                      if (e.key === "Escape") {
                        setEdgeInputValue("");
                        setEditingEdge(null);
                      }
                    }}
                    style={{
                      width: "100%",
                      height: "100%",
                      textAlign: "center",
                      fontSize: "12px",
                      border: "1px solid var(--accent)",
                      borderRadius: "3px",
                      background: "#fff",
                      color: "var(--text-h)",
                      outline: "none",
                      boxSizing: "border-box",
                    }}
                  />
                </foreignObject>
              );
            }

            return (
              <g
                key={`edge-label-group-${i}`}
                style={{ cursor: "pointer" }}
                onClick={(e) => {
                  e.stopPropagation();
                  setEditingEdge(i);
                  setEdgeInputValue(displayLen);
                }}
              >
                <rect
                  x={screenMidX - 25}
                  y={screenMidY - 11}
                  width="50"
                  height="22"
                  rx="3"
                  fill="#FFFFFF"
                  stroke="var(--border)"
                  strokeWidth="1"
                />
                <text
                  x={screenMidX}
                  y={screenMidY}
                  fill="#6B6B6B"
                  fontSize="11"
                  textAnchor="middle"
                  dominantBaseline="central"
                >
                  {displayLen}м
                </text>
              </g>
            );
          })}

          {safePoints.map((p, i) => (
            <circle
              key={i}
              cx={(p.x - offsetX) * scale}
              cy={(p.y - offsetY) * scale}
              r={draggingIdx === i ? "6.5" : "5"}
              fill={draggingIdx === i ? "var(--accent)" : "#FFFFFF"}
              stroke="var(--accent)"
              strokeWidth="1.4"
              onPointerDown={(e) => handleDeletePoint(i, e)}
              style={{ cursor: "grab" }}
            />
          ))}
        </svg>
      </div>

      {controlButtonsJSX}
    </div>
  );
}
