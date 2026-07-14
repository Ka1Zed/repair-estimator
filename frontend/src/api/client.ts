import type { Project, ProjectSummary, ProjectPayload, SharedProject } from "../types/project";

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

  // 5b. Доступность магазинов материалов по городу (GET /api/regions/stores, #363/#365)
  async fetchStores(city: string): Promise<{ city: string; stores: { name: string; available: boolean }[] }> {
    return this.request<{ city: string; stores: { name: string; available: boolean }[] }>(
      `/api/regions/stores?city=${encodeURIComponent(city)}`,
    );
  }

  // 6. Проекты
  async listProjects(): Promise<ProjectSummary[]> {
    return this.request<ProjectSummary[]>("/api/projects");
  }

  async createProject(data: ProjectPayload): Promise<Project> {
    return this.request<Project>("/api/projects", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async getProject(id: number): Promise<Project> {
    return this.request<Project>(`/api/projects/${id}`);
  }

  async updateProject(id: number, data: ProjectPayload): Promise<Project> {
    return this.request<Project>(`/api/projects/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
  }

  // 204 No Content — через общий request<T> нельзя, он всегда парсит JSON-тело.
  async deleteProject(id: number): Promise<void> {
    try {
      const response = await fetch(`${this.baseUrl}/api/projects/${id}`, {
        method: "DELETE",
      });
      if (!response.ok) throw new Error(`Ошибка HTTP: ${response.status} ${response.statusText}`);
    } catch (error) {
      console.error(`[API Error] Сбой при запросе к /api/projects/${id}:`, error);
      throw error;
    }
  }

  async getSharedProject(token: string): Promise<SharedProject> {
    return this.request<SharedProject>(`/api/projects/share/${token}`);
  }

  // 7. Загрузка чертежа (POST /api/blueprints/upload) — FormData, без Content-Type header
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

  // 8. Эталонный демо-чертёж (GET /api/blueprints/demo-image) — возвращает PNG blob
  async getDemoBlueprint(): Promise<Blob> {
    const response = await fetch(`${this.baseUrl}/api/blueprints/demo-image`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.blob();
  }
}

// Экспортируем готовый экземпляр класса
export const apiClient = new ApiClient(API_URL);
