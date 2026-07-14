import { describe, it, expect } from "vitest";
import { getDefaultRoomName, defaultWorksForRoomType } from "../store/projectStore";
import type { Room } from "../store/projectStore";

const makeRoom = (name: string): Room => ({
  id: "x",
  name,
  height: 2.7,
  room_type: "living",
  points: [],
  openings: [],
  works: defaultWorksForRoomType("living"),
});

describe("getDefaultRoomName", () => {
  it("возвращает метку типа, если список пуст", () => {
    expect(getDefaultRoomName("living", [])).toBe("Жилая комната");
  });

  it("возвращает метку с суффиксом 2, если первое имя занято", () => {
    const rooms = [makeRoom("Жилая комната")];
    expect(getDefaultRoomName("living", rooms)).toBe("Жилая комната 2");
  });

  it("пропускает уже занятые номера", () => {
    const rooms = [makeRoom("Санузел"), makeRoom("Санузел 2")];
    expect(getDefaultRoomName("bathroom", rooms)).toBe("Санузел 3");
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
