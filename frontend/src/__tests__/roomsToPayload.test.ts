import { describe, it, expect } from "vitest";
import { roomsToCalcPayload } from "../utils/roomsToPayload";
import type { Room } from "../store/projectStore";
import { defaultWorksForRoomType } from "../store/projectStore";

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
