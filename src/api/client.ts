// Базовый URL бэкенда (можно менять в зависимости от настроек команды, обычно локально это localhost:5000 или 8080)
const BASE_URL = 'http://localhost:5000/api';

// Интерфейс для данных комнаты, которую мы будем отправлять
interface RoomData {
  name: string;
  area: number;
}

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string) {
    style: this.baseUrl = baseUrl;
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
  async sendRoomData(roomData: RoomData): Promise<{ success: boolean; id?: string | number }> {
    return this.request<{ success: boolean; id?: string | number }>('/rooms', {
      method: 'POST',
      body: JSON.stringify(roomData),
    });
  }
}

// Экспортируем готовый экземпляр класса для использования на страницах
export const apiClient = new ApiClient(BASE_URL);