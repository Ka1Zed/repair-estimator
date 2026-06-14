interface Point {
  x: number | string;
  y: number | string;
}

interface Props {
  points: Point[];
}

export default function RoomPolygonPreview({ points }: Props) {
  if (points.length < 3) {
    return (
      <div style={{ color: "#888", marginTop: "20px" }}>
        Добавьте минимум 3 точки для отображения плана
      </div>
    );
  }

  // 1. Приводим всё к числам (пустые значения считаем за 0)
  const safePoints = points.map((p) => ({
    x: p.x === "-" || p.x === "" ? 0 : Number(p.x),
    y: p.y === "-" || p.y === "" ? 0 : Number(p.y),
  }));

  // 2. Ищем реальные границы фигуры по X и Y
  const xs = safePoints.map((p) => p.x);
  const ys = safePoints.map((p) => p.y);

  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);

  const rangeX = maxX - minX;
  const rangeY = maxY - minY;

  // Защита от деления на ноль (если вдруг все точки в одной координате)
  const effectiveRangeX = rangeX === 0 ? 1 : rangeX;
  const effectiveRangeY = rangeY === 0 ? 1 : rangeY;

  // 3. Задаем жесткие максимальные размеры рамки превью в пикселях
  const MAX_PREVIEW_WIDTH = 400;
  const MAX_PREVIEW_HEIGHT = 300;

  // 4. Оставляем 10% отступа по краям, чтобы белые кружочки не обрезались
  const paddingX = effectiveRangeX * 0.1;
  const paddingY = effectiveRangeY * 0.1;

  const totalViewWidth = effectiveRangeX + paddingX * 2;
  const totalViewHeight = effectiveRangeY + paddingY * 2;

  // 5. Вычисляем динамический масштаб (сколько пикселей в 1 метре ИМЕННО для этой фигуры)
  const scaleX = MAX_PREVIEW_WIDTH / totalViewWidth;
  const scaleY = MAX_PREVIEW_HEIGHT / totalViewHeight;
  const scale = Math.min(scaleX, scaleY); // Берем минимальный, чтобы пропорции не исказились

  // Итоговые размеры холста (они всегда будут меньше или равны 400x300)
  const svgWidth = totalViewWidth * scale;
  const svgHeight = totalViewHeight * scale;

  // Смещение, чтобы фигура всегда была по центру
  const offsetX = minX - paddingX;
  const offsetY = minY - paddingY;

  // Формируем новые координаты точек для SVG
  const pointsString = safePoints
    .map((p) => `${(p.x - offsetX) * scale},${(p.y - offsetY) * scale}`)
    .join(" ");

  return (
    <div style={{ marginTop: "20px", width: "100%", maxWidth: "450px" }}>
      <h3>Предпросмотр (макет):</h3>
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
        }}
      >
        <svg width={svgWidth} height={svgHeight} style={{ display: "block" }}>
          <defs>
            {/* Сетка теперь статичная (каждые 20px). Она не привязана к метрам, просто красивый фон */}
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
              r="5"
              fill="#fff"
              stroke="#5cba5c"
              strokeWidth="2"
            />
          ))}
        </svg>
      </div>
    </div>
  );
}
