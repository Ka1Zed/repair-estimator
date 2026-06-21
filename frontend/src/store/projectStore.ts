import { create } from "zustand";

export type RepairType = "cosmetic" | "basic" | "extended";

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
  floor?: string | boolean;
  walls?: string | boolean;
  ceiling?: string | boolean;
  tile?: boolean;
  electric?: string | boolean;
  plumbing?: boolean;
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
  setRepairType: (type: RepairType) => void;
  rooms: Room[];
  activeRoomIndex: number;
  addRoom: () => void;
  deleteRoom: (index: number) => void;
  setActiveRoom: (index: number) => void;
  updateRoomName: (index: number, name: string) => void;
  setHeight: (height: number | string) => void;
  updatePoint: (index: number, x: number | string, y: number | string) => void;
  setPoints: (points: Point[]) => void;
  addOpening: () => void;
  updateOpening: (openingIndex: number, field: "type" | "width" | "height", value: string | number) => void;
  deleteOpening: (openingIndex: number) => void;
  updateRepairOptions: (roomIndex: number, options: Partial<RepairOptions>) => void;
}

const createDefaultRoom = (name: string): Room => ({
  id: crypto.randomUUID(),
  name,
  height: 2.7,
  room_type: "living",
  points: [{ x: 0, y: 0 }, { x: 4, y: 0 }, { x: 4, y: 3 }, { x: 0, y: 3 }],
  openings: [],
  repair_options: { floor: false, walls: false, ceiling: false, tile: false, electric: false, plumbing: false }
});

export const useProjectStore = create<ProjectState>((set) => ({
  repair_type: "cosmetic",
  setRepairType: (type) => set({ repair_type: type }),
  rooms: [createDefaultRoom("Комната 1")],
  activeRoomIndex: 0,
  addRoom: () => set((state) => ({ rooms: [...state.rooms, createDefaultRoom(`Комната ${state.rooms.length + 1}`)], activeRoomIndex: state.rooms.length })),
  deleteRoom: (index) => set((state) => {
    const newRooms = state.rooms.filter((_, i) => i !== index);
    return { rooms: newRooms.length ? newRooms : [createDefaultRoom("Комната 1")], activeRoomIndex: Math.max(0, state.activeRoomIndex - 1) };
  }),
  setActiveRoom: (index) => set({ activeRoomIndex: index }),
  updateRoomName: (index, name) => set((state) => ({ rooms: state.rooms.map((r, i) => i === index ? { ...r, name } : r) })),
  setHeight: (height) => set((state) => ({ rooms: state.rooms.map((r, i) => i === state.activeRoomIndex ? { ...r, height } : r) })),
  updatePoint: (index, x, y) => set((state) => ({ rooms: state.rooms.map((r, i) => i === state.activeRoomIndex ? { ...r, points: r.points.map((p, pi) => pi === index ? { x, y } : p) } : r) })),
  setPoints: (points) => set((state) => ({ rooms: state.rooms.map((r, i) => i === state.activeRoomIndex ? { ...r, points } : r) })),
  addOpening: () => set((state) => ({ rooms: state.rooms.map((r, i) => i === state.activeRoomIndex ? { ...r, openings: [...r.openings, { id: crypto.randomUUID(), type: "door", width: 0.8, height: 2.0 }] } : r) })),
  updateOpening: (oI, f, v) => set((state) => ({ rooms: state.rooms.map((r, i) => i === state.activeRoomIndex ? { ...r, openings: r.openings.map((o, oi) => oi === oI ? { ...o, [f]: v } : o) } : r) })),
  deleteOpening: (oI) => set((state) => ({ rooms: state.rooms.map((r, i) => i === state.activeRoomIndex ? { ...r, openings: r.openings.filter((_, oi) => oi !== oI) } : r) })),
  updateRepairOptions: (rI, opt) => set((state) => ({ rooms: state.rooms.map((r, i) => i === rI ? { ...r, repair_options: { ...r.repair_options, ...opt } } : r) })),
}));