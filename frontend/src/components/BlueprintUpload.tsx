import { useRef, useState } from "react";
import { useProjectStore } from "../store/projectStore";

interface Point {
  x: number;
  y: number;
}

interface Opening {
  type: "door" | "window";
  width: number;
  height: number;
}

interface BlueprintResult {
  success: boolean;
  method: string;
  confidence: number;
  points: Point[];
  height: number | null;
  openings: Opening[];
  raw_dimensions: string[];
  warnings: string[];
}

const METHOD_LABEL: Record<string, string> = {
  gemini: "Gemini Vision",
  claude: "Claude Vision",
  ollama: "Ollama LLaVA",
  ocr: "EasyOCR",
  none: "—",
};

const CONFIDENCE_COLOR = (c: number) =>
  c >= 0.7 ? "#4caf50" : c >= 0.4 ? "#ff9800" : "#f44336";

export default function BlueprintUpload() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<BlueprintResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [applied, setApplied] = useState(false);

  const setPoints = useProjectStore((s) => s.setPoints);
  const setHeight = useProjectStore((s) => s.setHeight);

  const handleFile = async (file: File) => {
    setError(null);
    setResult(null);
    setApplied(false);
    setUploading(true);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch("/api/blueprints/upload", {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? `HTTP ${res.status}`);
      }

      const data: BlueprintResult = await res.json();
      setResult(data);

      // Автоприменение при высокой уверенности
      if (data.confidence >= 0.7 && data.points.length >= 3) {
        applyResult(data);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Неизвестная ошибка");
    } finally {
      setUploading(false);
    }
  };

  const applyResult = (r: BlueprintResult) => {
    if (r.points.length >= 3) {
      setPoints(r.points);
    }
    if (r.height !== null) {
      setHeight(String(r.height));
    }
    setApplied(true);
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
    e.target.value = "";
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  };

  const labelStyle: React.CSSProperties = {
    fontSize: "11px",
    letterSpacing: ".16em",
    textTransform: "uppercase",
    color: "#B0B0B0",
    marginBottom: "8px",
    display: "flex",
    alignItems: "center",
    gap: "8px",
  };

  const dropzoneStyle: React.CSSProperties = {
    border: "1.5px dashed var(--border)",
    borderRadius: "6px",
    padding: "20px",
    textAlign: "center",
    cursor: uploading ? "not-allowed" : "pointer",
    color: "#6B6B6B",
    fontSize: "13px",
    transition: "border-color 0.15s",
  };

  return (
    <div style={{ marginBottom: "20px" }}>
      <div style={labelStyle}>
        Загрузить чертёж
        <span
          style={{
            fontSize: "10px",
            background: "#2a2a2a",
            color: "#B0B0B0",
            border: "1px solid var(--border)",
            borderRadius: "3px",
            padding: "1px 6px",
            letterSpacing: ".08em",
          }}
        >
          beta
        </span>
      </div>

      <input
        ref={inputRef}
        type="file"
        accept=".png,.jpg,.jpeg,.pdf"
        style={{ display: "none" }}
        onChange={handleChange}
      />

      <div
        style={dropzoneStyle}
        onClick={() => !uploading && inputRef.current?.click()}
        onDrop={handleDrop}
        onDragOver={(e) => e.preventDefault()}
      >
        {uploading ? (
          "Обработка чертежа..."
        ) : (
          <>
            PNG / JPG / PDF · до 10 MB
            <br />
            <span style={{ fontSize: "12px", color: "#B0B0B0" }}>
              нажмите или перетащите файл
            </span>
          </>
        )}
      </div>

      {error && (
        <div
          style={{
            marginTop: "10px",
            padding: "10px",
            background: "#2a1a1a",
            border: "1px solid #6b2020",
            borderRadius: "4px",
            color: "#f44336",
            fontSize: "13px",
          }}
        >
          {error}
        </div>
      )}

      {result && (
        <div
          style={{
            marginTop: "12px",
            padding: "12px",
            background: "#1e1e1e",
            border: "1px solid var(--border)",
            borderRadius: "6px",
            fontSize: "13px",
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: "8px",
            }}
          >
            <span style={{ color: "#B0B0B0" }}>
              {METHOD_LABEL[result.method] ?? result.method}
            </span>
            <span
              style={{
                color: CONFIDENCE_COLOR(result.confidence),
                fontWeight: 500,
              }}
            >
              {Math.round(result.confidence * 100)}% уверенность
            </span>
          </div>

          <div style={{ color: "#ccc", marginBottom: "6px" }}>
            Точек: {result.points.length}
            {result.height !== null && ` · Высота: ${result.height} м`}
            {result.openings.length > 0 &&
              ` · Проёмов: ${result.openings.length}`}
          </div>

          {result.raw_dimensions.length > 0 && (
            <div style={{ color: "#6B6B6B", marginBottom: "6px", fontSize: "12px" }}>
              {result.raw_dimensions.join(", ")}
            </div>
          )}

          {result.warnings.map((w, i) => (
            <div
              key={i}
              style={{
                color: "#ff9800",
                fontSize: "12px",
                marginBottom: "4px",
              }}
            >
              ⚠ {w}
            </div>
          ))}

          {result.points.length >= 3 && (
            <button
              onClick={() => applyResult(result)}
              disabled={applied}
              style={{
                marginTop: "10px",
                padding: "7px 14px",
                background: applied ? "#2a2a2a" : "var(--text-h)",
                color: applied ? "#6B6B6B" : "#fff",
                border: "none",
                borderRadius: "3px",
                fontSize: "12px",
                cursor: applied ? "default" : "pointer",
              }}
            >
              {applied ? "Применено" : "Применить точки"}
            </button>
          )}

          <p
            style={{
              margin: "10px 0 0",
              fontSize: "11px",
              color: "#6B6B6B",
              fontStyle: "italic",
            }}
          >
            Результат требует ручной проверки
          </p>
        </div>
      )}
    </div>
  );
}
