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

  // Приводим к числам, пустой ввод или знак минуса временно интерпретируем как 0
  const safePoints = points.map((p) => ({
    x: p.x === "-" || p.x === "" ? 0 : Number(p.x),
    y: p.y === "-" || p.y === "" ? 0 : Number(p.y),
  }));

  const xs = safePoints.map((p) => p.x);
  const ys = safePoints.map((p) => p.y);

  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);

  // Добавляем запасной отступ в 1 метр вокруг фигуры
  const padding = 1;
  const svgMinX = minX - padding;
  const svgMinY = minY - padding;
  const svgMaxX = maxX + padding;
  const svgMaxY = maxY + padding;

  const scale = 50; // 1 метр = 50 пикселей

  const widthPixels = (svgMaxX - svgMinX) * scale;
  const heightPixels = (svgMaxY - svgMinY) * scale;

  const pointsString = safePoints
    .map((p) => `${p.x * scale},${p.y * scale}`)
    .join(" ");

  return (
    <div style={{ marginTop: "20px" }}>
      <h3>Предпросмотр:</h3>
      <div
        style={{
          background: "#222",
          padding: "20px",
          borderRadius: "8px",
          display: "inline-block",
        }}
      >
        <svg
          width={widthPixels}
          height={heightPixels}
          viewBox={`${svgMinX * scale} ${svgMinY * scale} ${widthPixels} ${heightPixels}`}
          style={{ display: "block" }}
        >
          <defs>
            <pattern
              id="grid"
              width={scale}
              height={scale}
              patternUnits="userSpaceOnUse"
            >
              <path
                d={`M ${scale} 0 L 0 0 0 ${scale}`}
                fill="none"
                stroke="#333"
                strokeWidth="1"
              />
            </pattern>
          </defs>

          {/* Сетка динамически подстраивается под сдвинутые координаты холста */}
          <rect
            x={svgMinX * scale}
            y={svgMinY * scale}
            width={widthPixels}
            height={heightPixels}
            fill="url(#grid)"
          />

          <polygon
            points={pointsString}
            fill="rgba(100, 200, 100, 0.3)"
            stroke="#5cba5c"
            strokeWidth="3"
          />

          {safePoints.map((p, i) => (
            <circle
              key={i}
              cx={p.x * scale}
              cy={p.y * scale}
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
