import type { CeilingShape, Room } from "../store/projectStore";

// ceiling_shape всегда отправляется целиком (в т.ч. для "flat" с пустыми числовыми
// полями) — бэкенд игнорирует levels/step_height_m/slope_deg вне своего type.
function ceilingShapePayload(shape: CeilingShape) {
  return {
    type: shape.type,
    levels: shape.levels != null ? Number(shape.levels) : null,
    step_height_m: shape.step_height_m != null ? Number(shape.step_height_m) : null,
    slope_deg: shape.slope_deg != null ? Number(shape.slope_deg) : null,
  };
}

export function roomsToCalcPayload(rooms: Room[]) {
  return rooms.map((room) => ({
    name: room.name,
    room_type: room.room_type,
    height: Number(room.height),
    openings: room.openings.map((op) => ({
      ...op,
      width: Number(op.width),
      height: Number(op.height),
    })),
    points: room.points.map((p) => ({ x: Number(p.x), y: Number(p.y) })),
    works: room.works,
    ceiling_shape: ceilingShapePayload(room.ceilingShape),
  }));
}
