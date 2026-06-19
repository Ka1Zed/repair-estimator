export interface Point {
  x: number;
  y: number;
}

// Пока ставим заглушку для проемов (окон/дверей), так как ими займемся позже
export interface Opening {
  id?: string;
  type?: string;
}

export interface Room {
  id: string; // Уникальный ID нужен реакту для ключей (keys)
  name: string;
  height: number;
  room_type: string;
  points: Point[];
  openings: Opening[];
}
