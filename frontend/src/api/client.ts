// Берем базовый URL из .env файла, если его нет - стучимся на локальный бэкенд FastAPI
const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

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

  // 2b. Расчёт геометрии одной комнаты (POST /api/rooms/calculate)
  async calculateRoomGeometry(payload: {
    height: number;
    points: { x: number; y: number }[];
  }): Promise<{ floor_area: number; ceiling_area: number; perimeter: number; wall_area: number }> {
    return this.request("/api/rooms/calculate", {
      method: "POST",
      body: JSON.stringify(payload),
    });
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
}

// Экспортируем готовый экземпляр класса
export const apiClient = new ApiClient(API_URL);
