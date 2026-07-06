import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { RoomTypeKey, FloorFinish, WallFinish, CeilingFinish } from "../types/roomTypes";
import { roomTypes } from "../types/roomTypes";
import { demoRoomData } from "../data/demoRoom";
import { uid } from "../utils/uid";

export interface Point {
  x: number | string;
  y: number | string;
}

export interface Opening {
  id: string;
  type: "door" | "window";
  width: number | string;
  height: number | string;
}

export interface RepairOptions {
  floor?: string | null;
  walls?: string | null;
  ceiling?: string | null;
  electric?: string | null;
  plumbing?: boolean;
}

export interface FloorWorks {
  enabled: boolean;
  finish: FloorFinish | null;
}

export interface WallsWorks {
  enabled: boolean;
  finish: WallFinish | null;
  wallpaper_pattern: boolean;
  primer_two_coats: boolean;
}

export interface CeilingWorks {
  enabled: boolean;
  finish: CeilingFinish | null;
  primer_two_coats: boolean;
}

export interface ElectricWorks {
  enabled: boolean;
  sockets: number | null;
  lights: number | null;
  cable_m: number | null;
}

export interface PlumbingWorks {
  enabled: boolean;
  points: number | null;
  pipe_m: number | null;
}

export interface RoomWorks {
  floor: FloorWorks;
  walls: WallsWorks;
  ceiling: CeilingWorks;
  electric: ElectricWorks;
  plumbing: PlumbingWorks;
}

export function defaultWorksForRoomType(rt: RoomTypeKey): RoomWorks {
  const rule = roomTypes[rt];
  return {
    floor: { enabled: true, finish: rule.floor[0] ?? null },
    walls: { enabled: true, finish: rule.walls[0] ?? null, wallpaper_pattern: false, primer_two_coats: false },
    ceiling: { enabled: true, finish: rule.ceiling[0] ?? null, primer_two_coats: false },
    electric: { enabled: true, sockets: 4, lights: 2, cable_m: null },
    plumbing: { enabled: rule.plumbing.required, points: rule.plumbing.required ? 2 : null, pipe_m: null },
  };
}

export interface Room {
  id: string;
  name: string;
  height: number | string;
  room_type: RoomTypeKey;
  points: Point[];
  openings: Opening[];
  works: RoomWorks;
}

interface ProjectState {
  city: string;
  rooms: Room[];
  activeRoomIndex: number;

  setCity: (city: string) => void;
  addRoom: () => void;
  deleteRoom: (index: number) => void;
  setActiveRoom: (index: number) => void;
  updateRoomName: (index: number, name: string) => void;
  updateActiveRoomType: (index: number, room_type: RoomTypeKey) => void;
  setHeight: (height: number | string) => void;
  updatePoint: (index: number, x: number | string, y: number | string) => void;
  setPoints: (points: Point[]) => void;
  addOpening: () => void;
  updateOpening: (
    openingIndex: number,
    field: "type" | "width" | "height",
    value: string | number,
  ) => void;
  deleteOpening: (openingIndex: number) => void;
  updateRoomWorks: (roomIndex: number, works: Partial<RoomWorks>) => void;
  clearActiveRoom: () => void;
  loadDemoRoom: () => void;
  resetProject: () => void;
}

const DEFAULT_REPAIR_OPTIONS: RepairOptions = {
  floor: null,
  walls: null,
  ceiling: null,
  electric: null,
  plumbing: false,
};

const createDefaultRoom = (name: string): Room => ({
  id: uid(),
  name,
  height: 2.7,
  room_type: "living",
  points: [
    { x: 0, y: 0 },
    { x: 4, y: 0 },
    { x: 4, y: 3 },
    { x: 0, y: 3 },
  ],
  openings: [],
  works: defaultWorksForRoomType("living"),
});

// Город по умолчанию совпадает с DEFAULT_REGION на бэкенде (app/api/regions.py):
// для него и для любого города без своих цен расчёт идёт по базовым seed-ценам.
const DEFAULT_CITY = "Казань";

const initialState = {
  city: DEFAULT_CITY,
  rooms: [createDefaultRoom("Комната 1")],
  activeRoomIndex: 0,
};

export const useProjectStore = create<ProjectState>()(
  persist(
    (set) => ({
      ...initialState,

      setCity: (city) => set({ city }),

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

      updateActiveRoomType: (index, room_type) =>
        set((state) => {
          const newRooms = [...state.rooms];
          newRooms[index] = {
            ...newRooms[index],
            room_type,
            works: defaultWorksForRoomType(room_type),
          };
          return { rooms: newRooms };
        }),

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

      addOpening: () =>
        set((state) => {
          const newRooms = [...state.rooms];
          const activeRoom = newRooms[state.activeRoomIndex];
          const newOpening: Opening = {
            id: uid(),
            type: "door",
            width: 0.8,
            height: 2.0,
          };
          newRooms[state.activeRoomIndex] = {
            ...activeRoom,
            openings: [...activeRoom.openings, newOpening],
          };
          return { rooms: newRooms };
        }),

      updateOpening: (openingIndex, field, value) =>
        set((state) => {
          const newRooms = [...state.rooms];
          const activeRoom = newRooms[state.activeRoomIndex];
          const newOpenings = [...activeRoom.openings];
          newOpenings[openingIndex] = { ...newOpenings[openingIndex], [field]: value };
          newRooms[state.activeRoomIndex] = { ...activeRoom, openings: newOpenings };
          return { rooms: newRooms };
        }),

      deleteOpening: (openingIndex) =>
        set((state) => {
          const newRooms = [...state.rooms];
          const activeRoom = newRooms[state.activeRoomIndex];
          newRooms[state.activeRoomIndex] = {
            ...activeRoom,
            openings: activeRoom.openings.filter((_, i) => i !== openingIndex),
          };
          return { rooms: newRooms };
        }),

      updateRoomWorks: (roomIndex, works) =>
        set((state) => {
          const newRooms = [...state.rooms];
          newRooms[roomIndex] = {
            ...newRooms[roomIndex],
            works: { ...newRooms[roomIndex].works, ...works },
          };
          return { rooms: newRooms };
        }),

      clearActiveRoom: () =>
        set((state) => {
          const newRooms = [...state.rooms];
          const activeRoom = newRooms[state.activeRoomIndex];
          newRooms[state.activeRoomIndex] = {
            ...activeRoom,
            points: [],
            openings: [],
          };
          return { rooms: newRooms };
        }),

      loadDemoRoom: () =>
        set((state) => {
          const newRooms = [...state.rooms];
          const activeRoom = newRooms[state.activeRoomIndex];
          newRooms[state.activeRoomIndex] = {
            ...activeRoom,
            height: demoRoomData.height,
            room_type: demoRoomData.room_type,
            points: [...demoRoomData.points],
            openings: demoRoomData.openings.map((op) => ({
              ...op,
              id: uid(),
            })),
          };
          return { rooms: newRooms };
        }),

      resetProject: () => set(initialState),
    }),
    {
      name: "repair-estimator-draft",
      version: 3,
      migrate: (persisted: unknown, version: number) => {
        let s = persisted as Record<string, unknown>;

        if (version < 2) {
          // v1 → v2: repair_options переехал из rooms[i] на уровень проекта
          const rooms = (s.rooms as Array<Record<string, unknown>>) ?? [];
          const fromRoom = rooms[0]?.repair_options as RepairOptions | undefined;
          s = {
            ...s,
            repair_options: fromRoom ?? { ...DEFAULT_REPAIR_OPTIONS },
            rooms: rooms.map((room) => {
              const r = { ...room };
              delete r['repair_options'];
              return r;
            }),
          };
        }

        if (version < 3) {
          // v2 → v3: works переехал на уровень каждой комнаты
          const rooms = (s.rooms as Array<Record<string, unknown>>) ?? [];
          s = {
            ...s,
            rooms: rooms.map((room) => {
              if (room.works) return room;
              const rt = (room.room_type as RoomTypeKey) ?? "living";
              return { ...room, works: defaultWorksForRoomType(rt) };
            }),
          };
        }

        return s;
      },
    },
  ),
);
