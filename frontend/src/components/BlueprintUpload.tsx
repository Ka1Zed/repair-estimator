import { useRef, useState } from "react";
import { useProjectStore } from "../store/projectStore";
import { apiClient } from "../api/client";
import BlueprintReview from "./BlueprintReview";
import styles from "./BlueprintUpload.module.css";

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
  fixture: "Демо-фикстура",
  none: "—",
};

const confidenceClass = (c: number) =>
  c >= 0.7 ? styles.confidenceHigh : c >= 0.4 ? styles.confidenceMid : styles.confidenceLow;

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

  const handleLoadDemo = async () => {
    setError(null);
    setResult(null);
    setReviewing(false);
    setUploading(true);
    if (imageUrl) URL.revokeObjectURL(imageUrl);
    try {
      const blob = await apiClient.getDemoBlueprint();
      setImageUrl(URL.createObjectURL(blob));
      const formData = new FormData();
      formData.append("file", new File([blob], "demo_room.png", { type: "image/png" }));
      const data = (await apiClient.uploadBlueprint(formData)) as BlueprintResult;
      setResult(data);
      if (data.points.length >= 3) setReviewing(true);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Неизвестная ошибка");
    } finally {
      setUploading(false);
    }
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

  return (
    <div className={styles.wrapper}>
      <div className={styles.labelRow}>
        Загрузить чертёж
        <span className={styles.betaBadge}>
          beta
        </span>
      </div>

      <input
        ref={inputRef}
        type="file"
        accept=".png,.jpg,.jpeg,.pdf"
        className={styles.hiddenInput}
        onChange={handleChange}
      />

      <div
        className={`${styles.dropzone} ${uploading ? styles.dropzoneDisabled : ""}`}
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
            <span className={styles.dropzoneHint}>
              нажмите или перетащите файл
            </span>
          </>
        )}
      </div>

      <div className={styles.demoRow}>
        <button
          className={styles.demoBtn}
          onClick={handleLoadDemo}
          disabled={uploading}
          title="Загрузить эталонный чертёж гостиной 4×3м — результат предзаписан, LLM не вызывается"
        >
          Попробовать демо-чертёж
        </button>
        <span className={styles.demoHint}>гарантированно работает без API-ключей</span>
      </div>

      {error && (
        <div className={styles.errorBox}>
          {error}
        </div>
      )}

      {result && (
        <div className={styles.resultBox}>
          <div className={styles.resultHeader}>
            <span className={styles.resultMethod}>
              {METHOD_LABEL[result.method] ?? result.method}
            </span>
            <span className={`${styles.confidence} ${confidenceClass(result.confidence)}`}>
              {Math.round(result.confidence * 100)}% уверенность
            </span>
          </div>

          <div className={styles.resultMeta}>
            Точек: {result.points.length}
            {result.height !== null && ` · Высота: ${result.height} м`}
            {result.openings.length > 0 &&
              ` · Проёмов: ${result.openings.length}`}
          </div>

          {result.raw_dimensions.length > 0 && (
            <div className={styles.rawDimensions}>
              {result.raw_dimensions.join(", ")}
            </div>
          )}

          {result.warnings.map((w, i) => (
            <div key={i} className={styles.warningRow}>
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
            <p className={styles.appliedHint}>
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
