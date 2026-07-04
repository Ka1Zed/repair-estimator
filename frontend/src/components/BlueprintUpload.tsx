import { useRef, useState } from "react";
import { useProjectStore } from "../store/projectStore";
import { apiClient } from "../api/client";
import BlueprintReview from "./BlueprintReview";

interface Point {
  x: number;
  y: number;
  nx?: number;
  ny?: number;
}

interface Opening {
  type: "door" | "window";
  width: number;
  height: number;
}

export interface BlueprintResult {
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
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reviewing, setReviewing] = useState(false);

  const setPoints = useProjectStore((s) => s.setPoints);
  const setHeight = useProjectStore((s) => s.setHeight);

  const handleFile = async (file: File) => {
    setError(null);
    setResult(null);
    setReviewing(false);
    setUploading(true);
    // Старый превью-URL больше не нужен — освобождаем
    if (imageUrl) URL.revokeObjectURL(imageUrl);
    setImageUrl(URL.createObjectURL(file));

    const formData = new FormData();
    formData.append("file", file);

    try {
      const data = (await apiClient.uploadBlueprint(formData)) as BlueprintResult;
      setResult(data);
      // Никакого авто-применения: ведём через ручную проверку и калибровку
      if (data.points.length >= 3) setReviewing(true);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Неизвестная ошибка");
    } finally {
      setUploading(false);
    }
  };

  const handleApply = (points: Point[], height: number | null) => {
    setPoints(points);
    if (height !== null) setHeight(String(height));
    setReviewing(false);
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
    color: "var(--text)",
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
    color: "var(--text)",
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
            background: "var(--accent-bg)",
            color: "var(--accent)",
            border: "1px solid var(--accent-border)",
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
            <span style={{ fontSize: "12px", color: "var(--text)" }}>
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
            background: "#fdecea",
            border: "1px solid #f5c6c2",
            borderRadius: "4px",
            color: "#c0392b",
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
            background: "var(--bg-canvas)",
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
            <span style={{ color: "var(--text)" }}>
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

          <div style={{ color: "var(--text-h)", marginBottom: "6px" }}>
            Точек: {result.points.length}
            {result.height !== null && ` · Высота: ${result.height} м`}
            {result.openings.length > 0 &&
              ` · Проёмов: ${result.openings.length}`}
          </div>

          {result.raw_dimensions.length > 0 && (
            <div style={{ color: "var(--text)", marginBottom: "6px", fontSize: "12px" }}>
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

          {reviewing && imageUrl && result.points.length >= 3 ? (
            <BlueprintReview
              imageUrl={imageUrl}
              result={result}
              onApply={handleApply}
              onCancel={() => setReviewing(false)}
            />
          ) : (
            <p
              style={{
                margin: "10px 0 0",
                fontSize: "11px",
                color: "var(--text)",
                fontStyle: "italic",
              }}
            >
              {result.points.length >= 3
                ? "Точки применены в редактор"
                : "Не удалось распознать контур — нужно минимум 3 точки"}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
