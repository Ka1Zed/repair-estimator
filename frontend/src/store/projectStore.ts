import { create } from "zustand";

export type RepairType = "cosmetic" | "basic" | "extended";

// РАЗРЕШИЛИ СТРОКИ: x и y теперь могут быть number или string
export interface Point {
  x: number | string;
  y: number | string;
}

interface ProjectState {
  repair_type: RepairType;
  setRepairType: (type: RepairType) => void;

  points: Point[];
  // И здесь тоже разрешили строки
  updatePoint: (index: number, x: number | string, y: number | string) => void;
  setPoints: (points: Point[]) => void;
}

export const useProjectStore = create<ProjectState>((set) => ({
  repair_type: "cosmetic",
  setRepairType: (type) => set({ repair_type: type }),

  points: [
    { x: 0, y: 0 },
    { x: 4, y: 0 },
    { x: 4, y: 3 },
    { x: 0, y: 3 },
  ],

  updatePoint: (index, x, y) =>
    set((state) => {
      const newPoints = [...state.points];
      newPoints[index] = { x, y };
      return { points: newPoints };
    }),

  setPoints: (points) => set({ points }),
}));
