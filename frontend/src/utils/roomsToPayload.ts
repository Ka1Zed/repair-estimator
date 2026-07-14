import type { Room } from "../store/projectStore";

export function roomsToPayload(rooms: Room[]) {
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
  }));
}
