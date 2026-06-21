export const finishOptions = {
  floor: { laminate: "Ламинат", linoleum: "Линолеум", parquet: "Паркет", tile: "Плитка" },
  walls: { paint: "Покраска", wallpaper: "Обои", tile: "Плитка", moisture_paint: "Влагостойкая краска" },
  ceiling: { paint: "Покраска", moisture_paint: "Влагостойкая краска", stretch: "Натяжной" },
  electric: { basic: "Базовая", extended: "Расширенная" }
};

export interface RoomTypeConfig {
  floor: string[];
  walls: string[];
  ceiling: string[];
  electric: string[];
  tile: boolean;
  plumbing: { available: boolean; required: boolean };
}

export const roomTypesMatrix: Record<string, RoomTypeConfig> = {
  living: {
    floor: ["laminate", "linoleum", "parquet"],
    walls: ["paint", "wallpaper"],
    ceiling: ["paint", "stretch"],
    electric: ["basic", "extended"],
    tile: false,
    plumbing: { available: false, required: false }
  },
  kitchen: {
    floor: ["tile", "laminate"],
    walls: ["paint", "tile"],
    ceiling: ["paint", "stretch"],
    electric: ["basic", "extended"],
    tile: true,
    plumbing: { available: true, required: false }
  },
  bathroom: {
    floor: ["tile"],
    walls: ["tile", "moisture_paint"],
    ceiling: ["moisture_paint", "stretch"],
    electric: ["basic", "extended"],
    tile: true,
    plumbing: { available: true, required: true }
  },
  hallway: {
    floor: ["laminate", "tile"],
    walls: ["paint", "wallpaper"],
    ceiling: ["paint", "stretch"],
    electric: ["basic", "extended"],
    tile: false,
    plumbing: { available: false, required: false }
  }
};