import { describe, it, expect } from "vitest";
import { roomsToCalcPayload } from "../utils/roomsToPayload";
import type { Room } from "../store/projectStore";
import { DEFAULT_CEILING_SHAPE, defaultWorksForRoomType } from "../store/projectStore";

const baseRoom: Room = {
  id: "r1",
  name: "Тестовая",
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
  ceilingShape: { ...DEFAULT_CEILING_SHAPE },
};

describe("roomsToCalcPayload", () => {
  it("конвертирует строковую высоту в число", () => {
    const room: Room = { ...baseRoom, height: "3.1" };
    const [out] = roomsToCalcPayload([room]);
    expect(out.height).toBe(3.1);
    expect(typeof out.height).toBe("number");
  });

  it("конвертирует строковые координаты точек в числа", () => {
    const room: Room = {
      ...baseRoom,
      points: [
        { x: "0", y: "0" },
        { x: "5.5", y: "3.2" },
      ],
    };
    const [out] = roomsToCalcPayload([room]);
    expect(out.points).toEqual([
      { x: 0, y: 0 },
      { x: 5.5, y: 3.2 },
    ]);
  });

  it("конвертирует строковые размеры проёмов в числа", () => {
    const room: Room = {
      ...baseRoom,
      openings: [{ id: "o1", type: "door", width: "0.8", height: "2.0" }],
    };
    const [out] = roomsToCalcPayload([room]);
    expect(out.openings[0].width).toBe(0.8);
    expect(out.openings[0].height).toBe(2);
  });

  it("сохраняет id и type проёма", () => {
    const room: Room = {
      ...baseRoom,
      openings: [{ id: "op-abc", type: "window", width: 1.2, height: 1.4 }],
    };
    const [out] = roomsToCalcPayload([room]);
    expect(out.openings[0].id).toBe("op-abc");
    expect(out.openings[0].type).toBe("window");
  });

  it("сохраняет works без изменений", () => {
    const works = defaultWorksForRoomType("bathroom");
    const room: Room = { ...baseRoom, room_type: "bathroom", works };
    const [out] = roomsToCalcPayload([room]);
    expect(out.works).toBe(works);
  });

  it("дефолтная форма потолка -> flat со всеми null-полями", () => {
    const [out] = roomsToCalcPayload([baseRoom]);
    expect(out.ceiling_shape).toEqual({
      type: "flat",
      levels: null,
      step_height_m: null,
      slope_deg: null,
    });
  });

  it("конвертирует строковые числа формы потолка", () => {
    const room: Room = {
      ...baseRoom,
      ceilingShape: { type: "multilevel", levels: "2" as unknown as number, step_height_m: "0.1" as unknown as number, slope_deg: null },
    };
    const [out] = roomsToCalcPayload([room]);
    expect(out.ceiling_shape).toEqual({
      type: "multilevel",
      levels: 2,
      step_height_m: 0.1,
      slope_deg: null,
    });
  });

  it("обрабатывает несколько комнат", () => {
    const rooms: Room[] = [
      { ...baseRoom, id: "r1", name: "Комната 1" },
      { ...baseRoom, id: "r2", name: "Комната 2" },
    ];
    const out = roomsToCalcPayload(rooms);
    expect(out).toHaveLength(2);
    expect(out[0].name).toBe("Комната 1");
    expect(out[1].name).toBe("Комната 2");
  });
});
