// VITE_API_URL задаётся только для cross-origin деплоев (см. README).
// По умолчанию — пустая строка: запросы уходят на тот же origin, а Vite-прокси
// (dev) и nginx (prod) маршрутизируют /api/* и /health на бэкенд.
const API_URL = import.meta.env.VITE_API_URL ?? "";

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  // Общий вспомогательный метод для выполнения запросов и обработки базовых ошибок
  private async request<T>(
    endpoint: string,
    options?: RequestInit,
  ): Promise<T> {
    try {
      const response = await fetch(`${this.baseUrl}${endpoint}`, {
        ...options,
        headers: {
          "Content-Type": "application/json",
          ...(options?.headers || {}),
        },
      });

      // Обработка ошибок сервера (например, 400 или 500)
      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(
          `Ошибка HTTP: ${response.status} ${errorText || response.statusText}`,
        );
      }

      return (await response.json()) as T;
    } catch (error) {
      // Обработка сетевых ошибок (если сервер выключен или упал интернет)
      console.error(`[API Error] Сбой при запросе к ${endpoint}:`, error);

      // Пробрасываем понятную ошибку и прикрепляем оригинальную (cause) для строгого линтера
      throw new Error(
        error instanceof Error
          ? error.message
          : "Сервер недоступен. Проверьте подключение к интернету или статус сервера.",
        { cause: error },
      );
    }
  }

  // 1. Проверка здоровья сервера (GET /health)
  async checkHealth(): Promise<{ status: string }> {
    return this.request<{ status: string }>("/health");
  }

  // 2. Получение справочника материалов (GET /api/materials)
  async fetchMaterials(): Promise<unknown> {
    return this.request<unknown>("/api/materials");
  }

  // 3. Получение справочника услуг (GET /api/labor-services)
  async fetchLaborServices(): Promise<unknown> {
    return this.request<unknown>("/api/labor-services");
  }

  // 4. Расчет сметы по новому контракту C1 (POST /api/estimates/calculate)
  async calculateEstimate(estimateData: unknown): Promise<unknown> {
    return this.request<unknown>("/api/estimates/calculate", {
      method: "POST",
      body: JSON.stringify(estimateData),
    });
  }

  // 5. Справочник городов для регионального ценообразования (GET /api/regions)
  async fetchRegions(): Promise<{ default: string; regions: string[] }> {
    return this.request<{ default: string; regions: string[] }>("/api/regions");
  }

  // 6. Загрузка чертежа (POST /api/blueprints/upload) — FormData, без Content-Type header
  async uploadBlueprint(formData: FormData): Promise<unknown> {
    const response = await fetch(`${this.baseUrl}/api/blueprints/upload`, {
      method: "POST",
      body: formData,
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error((body as { detail?: string }).detail ?? `HTTP ${response.status}`);
    }
    return response.json();
  }
}

// Экспортируем готовый экземпляр класса
export const apiClient = new ApiClient(API_URL);
