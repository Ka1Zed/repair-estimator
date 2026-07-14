import { describe, it, expect } from "vitest";
import { DEFAULT_CEILING_SHAPE, getDefaultRoomName, defaultWorksForRoomType } from "../store/projectStore";
import type { Room } from "../store/projectStore";

const makeRoom = (name: string): Room => ({
  id: "x",
  name,
  height: 2.7,
  room_type: "living",
  points: [],
  openings: [],
  works: defaultWorksForRoomType("living"),
  ceilingShape: { ...DEFAULT_CEILING_SHAPE },
});

describe("getDefaultRoomName", () => {
  it("для living возвращает нейтральное «Комната», если список пуст", () => {
    expect(getDefaultRoomName("living", [])).toBe("Комната");
  });

  it("возвращает метку с суффиксом 2, если первое имя занято", () => {
    const rooms = [makeRoom("Комната")];
    expect(getDefaultRoomName("living", rooms)).toBe("Комната 2");
  });

  it("пропускает уже занятые номера", () => {
    const rooms = [makeRoom("Влажное помещение"), makeRoom("Влажное помещение 2")];
    expect(getDefaultRoomName("bathroom", rooms)).toBe("Влажное помещение 3");
  });

  it("не зависит от ручных имён без совпадения", () => {
    const rooms = [makeRoom("Мастерская")];
    expect(getDefaultRoomName("kitchen", rooms)).toBe("Кухня");
  });
});

describe("defaultWorksForRoomType", () => {
  it("для living: plumbing.enabled = false", () => {
    const works = defaultWorksForRoomType("living");
    expect(works.plumbing.enabled).toBe(false);
  });

  it("для bathroom: plumbing.enabled = true", () => {
    const works = defaultWorksForRoomType("bathroom");
    expect(works.plumbing.enabled).toBe(true);
  });

  it("для bathroom: floor.finish = tile (первый допустимый)", () => {
    const works = defaultWorksForRoomType("bathroom");
    expect(works.floor.finish).toBe("tile");
  });

  it("wall_condition всегда normal по умолчанию", () => {
    for (const rt of ["living", "kitchen", "bathroom", "hallway"] as const) {
      expect(defaultWorksForRoomType(rt).walls.wall_condition).toBe("normal");
    }
  });
});
