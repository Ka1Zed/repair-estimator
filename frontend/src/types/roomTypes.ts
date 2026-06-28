// src/types/roomTypes.ts
// Канонический источник данных — docs/room-types.json.
// Здесь типизированная копия для фронта; при изменении JSON синхронизировать вручную.

export type RoomTypeKey = "living" | "kitchen" | "bathroom" | "hallway";
export type FloorFinish = "laminate" | "linoleum" | "parquet" | "tile";
export type WallFinish = "paint" | "wallpaper" | "tile" | "moisture_paint";
export type CeilingFinish = "paint" | "moisture_paint" | "stretch";
export type ElectricOption = "basic" | "extended";

export interface PlumbingRule {
  available: boolean;
  required: boolean;
}

export interface RoomTypeRule {
  label: string;
  floor: FloorFinish[];
  walls: WallFinish[];
  ceiling: CeilingFinish[];
  electric: ElectricOption[];
  plumbing: PlumbingRule;
}

export const finishOptions = {
  floor: {
    laminate: "Ламинат",
    linoleum: "Линолеум",
    parquet: "Паркет",
    tile: "Плитка",
  },
  walls: {
    paint: "Покраска",
    wallpaper: "Обои",
    tile: "Плитка",
    moisture_paint: "Влагостойкая краска",
  },
  ceiling: {
    paint: "Покраска",
    moisture_paint: "Влагостойкая краска",
    stretch: "Натяжной",
  },
  electric: { basic: "Базовая", extended: "Расширенная" },
} as const;

export const roomTypes: Record<RoomTypeKey, RoomTypeRule> = {
  living: {
    label: "Жилая комната",
    floor: ["laminate", "linoleum", "parquet"],
    walls: ["paint", "wallpaper"],
    ceiling: ["paint", "stretch"],
    electric: ["basic", "extended"],
    plumbing: { available: false, required: false },
  },
  kitchen: {
    label: "Кухня",
    floor: ["tile", "laminate"],
    walls: ["paint", "tile"],
    ceiling: ["paint", "stretch"],
    electric: ["basic", "extended"],
    plumbing: { available: true, required: false },
  },
  bathroom: {
    label: "Санузел",
    floor: ["tile"],
    walls: ["tile", "moisture_paint"],
    ceiling: ["moisture_paint", "stretch"],
    electric: ["basic", "extended"],
    plumbing: { available: true, required: true },
  },
  hallway: {
    label: "Коридор",
    floor: ["laminate", "tile"],
    walls: ["paint", "wallpaper"],
    ceiling: ["paint", "stretch"],
    electric: ["basic", "extended"],
    plumbing: { available: false, required: false },
  },
};

export const ROOM_TYPE_KEYS = Object.keys(roomTypes) as RoomTypeKey[];

// Список типов комнат для селектора: [{ key, label }]
export const roomTypeOptions = ROOM_TYPE_KEYS.map((key) => ({
  key,
  label: roomTypes[key].label,
}));

// Готовые опции работ для активного типа комнаты (ключ + подпись) — для дропдаунов/чекбоксов
export function allowedWorks(rt: RoomTypeKey) {
  const rule = roomTypes[rt];
  return {
    floor: rule.floor.map((k) => ({ key: k, label: finishOptions.floor[k] })),
    walls: rule.walls.map((k) => ({ key: k, label: finishOptions.walls[k] })),
    ceiling: rule.ceiling.map((k) => ({
      key: k,
      label: finishOptions.ceiling[k],
    })),
    electric: rule.electric.map((k) => ({
      key: k,
      label: finishOptions.electric[k],
    })),
    plumbing: rule.plumbing,
  };
}

// Точечные проверки
export const isPlumbingAvailable = (rt: RoomTypeKey) =>
  roomTypes[rt].plumbing.available;
export const isPlumbingRequired = (rt: RoomTypeKey) =>
  roomTypes[rt].plumbing.required;
