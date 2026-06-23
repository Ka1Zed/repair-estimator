import { useProjectStore } from "../store/projectStore";

export default function RoomsList() {
  const rooms = useProjectStore((state) => state.rooms);
  const activeRoomIndex = useProjectStore((state) => state.activeRoomIndex);

  const setActiveRoom = useProjectStore((state) => state.setActiveRoom);
  const addRoom = useProjectStore((state) => state.addRoom);
  const deleteRoom = useProjectStore((state) => state.deleteRoom);
  const updateRoomName = useProjectStore((state) => state.updateRoomName);

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "8px",
        flexWrap: "wrap",
        marginBottom: "32px",
      }}
    >
      {rooms.map((room, index) => {
        const active = activeRoomIndex === index;
        return (
          <div
            key={room.id}
            onClick={() => setActiveRoom(index)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "8px",
              padding: "7px 13px",
              border: active ? "1px solid var(--accent)" : "1px solid var(--border)",
              background: active ? "var(--bg-canvas)" : "transparent",
              borderRadius: "3px",
              cursor: "pointer",
              transition: "all .15s",
            }}
          >
            <input
              type="text"
              value={room.name}
              onChange={(e) => updateRoomName(index, e.target.value)}
              onClick={(e) => {
                e.stopPropagation();
                setActiveRoom(index);
              }}
              style={{
                background: "transparent",
                border: "none",
                outline: "none",
                fontSize: "12.5px",
                letterSpacing: ".01em",
                color: active ? "var(--text-h)" : "#6B6B6B",
                width: Math.max(64, room.name.length * 8),
              }}
            />

            {rooms.length > 1 && (
              <span
                onClick={(e) => {
                  e.stopPropagation();
                  deleteRoom(index);
                }}
                style={{
                  fontSize: "13px",
                  color: "#C4C4C4",
                  lineHeight: 1,
                  cursor: "pointer",
                }}
              >
                ×
              </span>
            )}
          </div>
        );
      })}

      <button
        onClick={addRoom}
        style={{
          background: "none",
          border: "none",
          cursor: "pointer",
          fontSize: "12.5px",
          color: "#9A9A9A",
          padding: "7px 6px",
          letterSpacing: ".01em",
        }}
      >
        + комната
      </button>
    </div>
  );
}
