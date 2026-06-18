import { useState, useRef } from "react";
import { useProjectStore } from "../store/projectStore";

export default function RoomPolygonEditor() {
  const points = useProjectStore((state) => state.points);
  const updatePoint = useProjectStore((state) => state.updatePoint);

  const [draggingIdx, setDraggingIdx] = useState<number | null>(null);
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

  // Отступы по бокам, чтобы точки не прилипали к краям
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

  const pointsString = safePoints
    .map((p) => `${(p.x - offsetX) * scale},${(p.y - offsetY) * scale}`)
    .join(" ");

  const handlePointerDown = (index: number) => {
    setDraggingIdx(index);
  };

  const handlePointerMove = (e: React.PointerEvent) => {
    if (draggingIdx === null || !svgRef.current) return;

    const svg = svgRef.current;

    // Получаем матрицу трансформации экрана (чтобы учесть, как браузер сжал нашу адаптивную SVG)
    const ctm = svg.getScreenCTM();
    if (!ctm) return;

    // Создаем системную точку SVG и записываем в нее координаты мыши на экране
    const pt = svg.createSVGPoint();
    pt.x = e.clientX;
    pt.y = e.clientY;

    // Магия: переводим экранные пиксели во внутренние пиксели SVG с учетом масштаба
    const cursorPt = pt.matrixTransform(ctm.inverse());

    let newRealX = cursorPt.x / scale + offsetX;
    let newRealY = cursorPt.y / scale + offsetY;

    // ЖЕСТКАЯ ГРАНИЦА: запрещаем отрицательные значения
    newRealX = Math.max(0, newRealX);
    newRealY = Math.max(0, newRealY);

    newRealX = Math.round(newRealX * 10) / 10;
    newRealY = Math.round(newRealY * 10) / 10;

    updatePoint(draggingIdx, newRealX, newRealY);
  };

  const handlePointerUp = () => {
    setDraggingIdx(null);
  };

  return (
    <div style={{ marginTop: "20px", width: "100%", maxWidth: "450px" }}>
      <h3>Редактор помещения:</h3>
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
          // ЗАМЕНИЛИ жесткие width и height на умный viewBox
          viewBox={`0 0 ${svgWidth} ${svgHeight}`}
          style={{
            display: "block",
            touchAction: "none",
            width: "100%", // Теперь ширина резиновая
            height: "auto", // Высота подстраивается под ширину
            maxHeight: "300px", // Ограничиваем только максимальный размер
            overflow: "visible",
          }}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerLeave={handlePointerUp}
        >
          <defs>
            <pattern
              id="grid"
              width="20"
              height="20"
              patternUnits="userSpaceOnUse"
            >
              <path
                d="M 20 0 L 0 0 0 20"
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

          {safePoints.map((p, i) => (
            <circle
              key={i}
              cx={(p.x - offsetX) * scale}
              cy={(p.y - offsetY) * scale}
              r={draggingIdx === i ? "8" : "6"}
              fill={draggingIdx === i ? "#5cba5c" : "#fff"}
              stroke="#5cba5c"
              strokeWidth="2"
              onPointerDown={() => handlePointerDown(i)}
              style={{ cursor: "grab" }}
            />
          ))}
        </svg>
      </div>
    </div>
  );
}
