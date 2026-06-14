interface Point {
  x: number;
  y: number;
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

  const maxX = Math.max(...points.map((p) => p.x));
  const maxY = Math.max(...points.map((p) => p.y));

  // Увеличиваем масштаб, чтобы метры стали видимыми на экране (1 метр = 50 пикселей)
  const scale = 50;
  const width = (maxX + 1) * scale;
  const height = (maxY + 1) * scale;

  const pointsString = points
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
        <svg width={width} height={height} style={{ overflow: "visible" }}>
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
          <rect width="100%" height="100%" fill="url(#grid)" />

          <polygon
            points={pointsString}
            fill="rgba(100, 200, 100, 0.3)"
            stroke="#5cba5c"
            strokeWidth="3"
          />

          {points.map((p, i) => (
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
