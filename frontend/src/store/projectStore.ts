import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { RoomTypeKey } from "../types/roomTypes";
import { demoRoomData } from "../data/demoRoom";

export type RepairType = "cosmetic" | "base" | "extended";

export interface Point {
  x: number | string;
  y: number | string;
}

export interface Opening {
  id: string;
  type: "door" | "window";
  // TODO: перед POST /api/estimates/calculate обязательно конвертировать width и height через Number()
  width: number | string;
  height: number | string;
}

export interface RepairOptions {
  floor?: string | null;
  walls?: string | null;
  ceiling?: string | null;
  tile?: boolean;
  electric?: string | null;
  plumbing?: boolean;
}

export interface Room {
  id: string;
  name: string;
  height: number | string;
  room_type: RoomTypeKey;
  points: Point[];
  openings: Opening[];
}

interface ProjectState {
  repair_type: RepairType;
  repair_options: RepairOptions;
  rooms: Room[];
  activeRoomIndex: number;

  setRepairType: (type: RepairType) => void;
  updateRepairOptions: (options: Partial<RepairOptions>) => void;
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
  clearActiveRoom: () => void;
  loadDemoRoom: () => void;
  resetProject: () => void;
}

const DEFAULT_REPAIR_OPTIONS: RepairOptions = {
  floor: null,
  walls: null,
  ceiling: null,
  tile: false,
  electric: null,
  plumbing: false,
};

const createDefaultRoom = (name: string): Room => ({
  id: crypto.randomUUID(),
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
});

const initialState = {
  repair_type: "cosmetic" as RepairType,
  repair_options: { ...DEFAULT_REPAIR_OPTIONS },
  rooms: [createDefaultRoom("Комната 1")],
  activeRoomIndex: 0,
};

export const useProjectStore = create<ProjectState>()(
  persist(
    (set) => ({
      ...initialState,

      setRepairType: (type) => set({ repair_type: type }),

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
          newRooms[index] = { ...newRooms[index], room_type };
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
            id: crypto.randomUUID(),
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

      updateRepairOptions: (options) =>
        set((state) => ({
          repair_options: { ...state.repair_options, ...options },
        })),

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
              id: crypto.randomUUID(),
            })),
          };
          return { rooms: newRooms };
        }),

      resetProject: () => set(initialState),
    }),
    {
      name: "repair-estimator-draft",
      version: 2,
      migrate: (persisted: unknown, version: number) => {
        const state = persisted as Record<string, unknown>;
        if (version === 1) {
          // repair_options переехал из rooms[i] на уровень проекта
          const rooms = (state.rooms as Array<Record<string, unknown>>) ?? [];
          const fromRoom = rooms[0]?.repair_options as RepairOptions | undefined;
          return {
            ...state,
            repair_options: fromRoom ?? { ...DEFAULT_REPAIR_OPTIONS },
            rooms: rooms.map(({ repair_options: _r, ...room }) => room),
          };
        }
        return state;
      },
    },
  ),
);
