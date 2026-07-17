import { describe, it, expect } from "vitest";
import { migrateProjectState } from "../store/projectStore";

describe("migrateProjectState", () => {
  it("v1 → v2: переносит repair_options из rooms[0] на уровень стейта, убирает из комнат", () => {
    const v1State = {
      city: "Казань",
      scope: "finish_only",
      rooms: [
        {
          id: "r1",
          name: "Жилая комната",
          height: 2.7,
          room_type: "living",
          points: [],
          openings: [],
          repair_options: { floor: "laminate", walls: "paint", ceiling: null, electric: null, plumbing: false },
        },
      ],
    };

    const result = migrateProjectState(v1State, 1);
    const rooms = result.rooms as Array<Record<string, unknown>>;

    expect(rooms[0]).not.toHaveProperty("repair_options");
    expect(result).toHaveProperty("repair_options");
    expect((result.repair_options as Record<string, unknown>).floor).toBe("laminate");
  });

  it("v2 → v3: добавляет works к комнатам, у которых его нет", () => {
    const v2State = {
      city: "Казань",
      scope: "finish_only",
      repair_options: { floor: null, walls: null, ceiling: null, electric: null, plumbing: false },
      rooms: [
        {
          id: "r1",
          name: "Санузел",
          height: 2.5,
          room_type: "bathroom",
          points: [],
          openings: [],
        },
      ],
    };

    const result = migrateProjectState(v2State, 2);
    const rooms = result.rooms as Array<Record<string, unknown>>;
    const works = rooms[0].works as Record<string, unknown>;

    expect(works).toBeDefined();
    const plumbing = works.plumbing as Record<string, unknown>;
    expect(plumbing.enabled).toBe(true);
  });

  it("v3 → v4: добавляет wall_condition: normal к walls без этого поля", () => {
    const v3State = {
      city: "Казань",
      scope: "finish_only",
      rooms: [
        {
          id: "r1",
          name: "Жилая комната",
          height: 2.7,
          room_type: "living",
          points: [],
          openings: [],
          works: {
            floor: { enabled: true, finish: "laminate" },
            walls: { enabled: true, finish: "paint", wallpaper_pattern: false, primer_two_coats: false },
            ceiling: { enabled: true, finish: "paint", primer_two_coats: false },
            electric: { enabled: true, sockets: 4, lights: 2, cable_m: null },
            plumbing: { enabled: false, points: null, pipe_m: null },
          },
        },
      ],
    };

    const result = migrateProjectState(v3State, 3);
    const rooms = result.rooms as Array<Record<string, unknown>>;
    const works = rooms[0].works as Record<string, unknown>;
    const walls = works.walls as Record<string, unknown>;

    expect(walls.wall_condition).toBe("normal");
  });

  it("v3 → v4: не перетирает уже существующий wall_condition", () => {
    const v3State = {
      rooms: [
        {
          id: "r1",
          room_type: "living",
          works: {
            walls: { enabled: true, finish: "paint", wall_condition: "uneven" },
          },
        },
      ],
    };

    const result = migrateProjectState(v3State, 3);
    const rooms = result.rooms as Array<Record<string, unknown>>;
    const walls = (rooms[0].works as Record<string, unknown>).walls as Record<string, unknown>;

    expect(walls.wall_condition).toBe("uneven");
  });

  it("v4 → v5: добавляет ceilingShape: flat к комнатам, у которых его нет", () => {
    const v4State = {
      city: "Казань",
      scope: "finish_only",
      rooms: [
        {
          id: "r1",
          name: "Жилая комната",
          height: 2.7,
          room_type: "living",
          points: [],
          openings: [],
          works: {},
        },
      ],
    };

    const result = migrateProjectState(v4State, 4);
    const rooms = result.rooms as Array<Record<string, unknown>>;
    const ceilingShape = rooms[0].ceilingShape as Record<string, unknown>;

    expect(ceilingShape.type).toBe("flat");
  });

  it("v4 → v5: не перетирает уже существующий ceilingShape", () => {
    const v4State = {
      rooms: [
        {
          id: "r1",
          room_type: "living",
          ceilingShape: { type: "multilevel", levels: 2, step_height_m: 0.1, slope_deg: null },
        },
      ],
    };

    const result = migrateProjectState(v4State, 4);
    const rooms = result.rooms as Array<Record<string, unknown>>;
    const ceilingShape = rooms[0].ceilingShape as Record<string, unknown>;

    expect(ceilingShape.type).toBe("multilevel");
    expect(ceilingShape.levels).toBe(2);
  });
});
