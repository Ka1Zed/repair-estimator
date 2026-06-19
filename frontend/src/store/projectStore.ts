import { create } from "zustand";

export type RepairType = "cosmetic" | "basic" | "extended";

export interface Point {
  x: number | string;
  y: number | string;
}

export interface Opening {
  id?: string;
  type?: string;
}

export interface Room {
  id: string;
  name: string;
  height: number;
  room_type: string;
  points: Point[];
  openings: Opening[];
}

interface ProjectState {
  repair_type: RepairType;
  setRepairType: (type: RepairType) => void;

  rooms: Room[];
  activeRoomIndex: number;

  addRoom: () => void;
  deleteRoom: (index: number) => void;
  setActiveRoom: (index: number) => void;
  updateRoomName: (index: number, name: string) => void;

  // ДОБАВЛЕНО: функция для изменения высоты
  setHeight: (height: number) => void;

  updatePoint: (index: number, x: number | string, y: number | string) => void;
  setPoints: (points: Point[]) => void;
}

const createDefaultRoom = (name: string): Room => ({
  id: crypto.randomUUID(),
  name,
  height: 2.7, // Дефолтная высота
  room_type: "living_room",
  points: [
    { x: 0, y: 0 },
    { x: 4, y: 0 },
    { x: 4, y: 3 },
    { x: 0, y: 3 },
  ],
  openings: [],
});

export const useProjectStore = create<ProjectState>((set) => ({
  repair_type: "cosmetic",
  setRepairType: (type) => set({ repair_type: type }),

  rooms: [createDefaultRoom("Комната 1")],
  activeRoomIndex: 0,

  addRoom: () =>
    set((state) => {
      const newRoom = createDefaultRoom(`Комната ${state.rooms.length + 1}`);
      return {
        rooms: [...state.rooms, newRoom],
        activeRoomIndex: state.rooms.length,
      };
    }),

  deleteRoom: (index) =>
    set((state) => {
      if (state.rooms.length <= 1) return state;

      const newRooms = state.rooms.filter((_, i) => i !== index);
      let newIndex = state.activeRoomIndex;

      if (newIndex >= newRooms.length) {
        newIndex = newRooms.length - 1;
      } else if (index < newIndex) {
        newIndex -= 1;
      }

      return { rooms: newRooms, activeRoomIndex: newIndex };
    }),

  setActiveRoom: (index) => set({ activeRoomIndex: index }),

  updateRoomName: (index, name) =>
    set((state) => {
      const newRooms = [...state.rooms];
      newRooms[index] = { ...newRooms[index], name };
      return { rooms: newRooms };
    }),

  // ДОБАВЛЕНО: реализация изменения высоты активной комнаты
  setHeight: (height) =>
    set((state) => {
      const newRooms = [...state.rooms];
      newRooms[state.activeRoomIndex] = {
        ...newRooms[state.activeRoomIndex],
        height,
      };
      return { rooms: newRooms };
    }),

  updatePoint: (index, x, y) =>
    set((state) => {
      const newRooms = [...state.rooms];
      const activeRoom = newRooms[state.activeRoomIndex];
      const newPoints = [...activeRoom.points];

      newPoints[index] = { x, y };
      newRooms[state.activeRoomIndex] = { ...activeRoom, points: newPoints };

      return { rooms: newRooms };
    }),

  setPoints: (points) =>
    set((state) => {
      const newRooms = [...state.rooms];
      newRooms[state.activeRoomIndex] = {
        ...newRooms[state.activeRoomIndex],
        points,
      };
      return { rooms: newRooms };
    }),
}));
