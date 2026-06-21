export const demoRoomData = {
  height: 2.7,
  room_type: "living" as const,
  points: [
    { x: 0, y: 0 },
    { x: 4, y: 0 },
    { x: 4, y: 3 },
    { x: 0, y: 3 },
  ],
  openings: [
    {
      id: crypto.randomUUID(),
      type: "door" as const,
      width: 0.8,
      height: 2.0,
    },
    {
      id: crypto.randomUUID(),
      type: "window" as const,
      width: 1.5,
      height: 1.4,
    },
  ],
};
