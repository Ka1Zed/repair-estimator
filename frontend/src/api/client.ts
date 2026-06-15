// Базовый URL бэкенда (можно менять в зависимости от настроек команды, обычно локально это localhost:5000 или 8080)
const BASE_URL = 'http://localhost:8000';

// Добавил - Точка помещения
interface Point {
  x: number;
  y: number;
}

// Интерфейс для данных комнаты, которую мы будем отправлять
// Обновил - Данные для расчёта (по контракту docs/api.md)
interface RoomData {
  height: number;
  points: Point[];
}

// Добавид - Ответ расчёта
interface CalculateResult {
  floor_area: number;
  ceiling_area: number;
  perimeter: number;
  wall_area: number;
}

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  // Общий вспомогательный метод для выполнения запросов и обработки базовых ошибок
  private async request<T>(endpoint: string, options?: RequestInit): Promise<T> {
    try {
      const response = await fetch(`${this.baseUrl}${endpoint}`, {
        ...options,
        headers: {
          'Content-Type': 'application/json',
          ...(options?.headers || {}),
        },
      });

      // Обработка ошибок сервера (4xx, 5xx)
      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Ошибка сервера (${response.status}): ${errorText || response.statusText}`);
      }

      // Если всё хорошо, возвращаем распарсенный JSON
      return await response.json() as T;
    } catch (error) {
      // Обработка сетевых ошибок (например, если бэкенд вообще выключен)
      console.error(`API Error on ${endpoint}:`, error);
      throw error instanceof Error ? error : new Error('Неизвестная сетевая ошибка');
    }
  }

  // 1. Функция проверки здоровья сервера (GET /health)
  async checkHealth(): Promise<{ status: string }> {
    // Обычно эндпоинт /health лежит в корне бэка, поэтому делаем запрос относительно корня или /api
    return this.request<{ status: string }>('/health');
  }

  // 2. Функция для отправки данных комнаты (POST /rooms или аналогичный эндпоинт)
  // Обновил - Отправка данных комнаты на расчёт (POST /api/rooms/calculate)
  async sendRoomData(roomData: RoomData): Promise<CalculateResult> {
    return this.request<CalculateResult>('/api/rooms/calculate', {
      method: 'POST',
      body: JSON.stringify(roomData),
    });
  }
}

// Экспортируем готовый экземпляр класса для использования на страницах
export const apiClient = new ApiClient(BASE_URL);