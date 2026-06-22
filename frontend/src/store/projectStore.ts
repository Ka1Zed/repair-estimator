import { create } from "zustand";
import { persist } from "zustand/middleware";
import { demoRoomData } from "../data/demoRoom";

export type RepairType = "cosmetic" | "basic" | "extended";

export interface RepairOptions {
  floor?: boolean;
  walls?: boolean;
  ceiling?: boolean;
  tile?: boolean;
  electric?: boolean;
  plumbing?: boolean;
}

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

export interface Room {
  id: string;
  name: string;
  height: number | string;
  room_type: string;
  points: Point[];
  openings: Opening[];
  repair_options?: RepairOptions;
}

interface ProjectState {
  repair_type: RepairType;
  rooms: Room[];
  activeRoomIndex: number;

  setRepairType: (type: RepairType) => void;
  addRoom: () => void;
  deleteRoom: (index: number) => void;
  setActiveRoom: (index: number) => void;
  updateRoomName: (index: number, name: string) => void;
  updateActiveRoomType: (index: number, room_type: string) => void;
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
  updateRepairOptions: (roomIndex: number, options: Partial<RepairOptions>) => void;
  clearActiveRoom: () => void;
  loadDemoRoom: () => void;
  resetProject: () => void;
}

const defaultRepairOptions: RepairOptions = {
  floor: false,
  walls: false,
  ceiling: false,
  tile: false,
  electric: false,
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
  repair_options: { ...defaultRepairOptions },
});

const initialState = {
  repair_type: "cosmetic" as RepairType,
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
          const newRoom = createDefaultRoom(
            `Комната ${state.rooms.length + 1}`,
          );
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
          newRooms[state.activeRoomIndex] = {
            ...activeRoom,
            points: newPoints,
          };

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

          newOpenings[openingIndex] = {
            ...newOpenings[openingIndex],
            [field]: value,
          };

          newRooms[state.activeRoomIndex] = {
            ...activeRoom,
            openings: newOpenings,
          };
          return { rooms: newRooms };
        }),

      deleteOpening: (openingIndex) =>
        set((state) => {
          const newRooms = [...state.rooms];
          const activeRoom = newRooms[state.activeRoomIndex];
          const newOpenings = activeRoom.openings.filter(
            (_, i) => i !== openingIndex,
          );

          newRooms[state.activeRoomIndex] = {
            ...activeRoom,
            openings: newOpenings,
          };
          return { rooms: newRooms };
        }),

      updateRepairOptions: (roomIndex, options) =>
        set((state) => {
          const newRooms = [...state.rooms];
          newRooms[roomIndex] = {
            ...newRooms[roomIndex],
            repair_options: { ...newRooms[roomIndex].repair_options, ...options },
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
            repair_options: { ...defaultRepairOptions },
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
      version: 1,
    },
  ),
);
