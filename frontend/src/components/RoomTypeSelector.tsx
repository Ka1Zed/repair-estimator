import { useProjectStore } from "../store/projectStore";
import { roomTypeOptions, type RoomTypeKey } from "../types/roomTypes";

export const RoomTypeSelector = () => {
  const activeRoomIndex = useProjectStore((state) => state.activeRoomIndex);
  const rooms = useProjectStore((state) => state.rooms);
  const updateActiveRoomType = useProjectStore(
    (state) => state.updateActiveRoomType,
  );

  const activeRoom = rooms[activeRoomIndex];

  if (!activeRoom) return null;

  return (
    <div style={{ marginBottom: "15px" }}>
      <label
        htmlFor="room-type"
        style={{ display: "block", marginBottom: "5px", color: "#fff" }}
      >
        Тип комнаты:
      </label>
      <select
        id="room-type"
        value={activeRoom.room_type}
        onChange={(e) => updateActiveRoomType(e.target.value as RoomTypeKey)}
        style={{
          width: "100%",
          padding: "6px",
          marginTop: "5px",
          background: "#333",
          color: "#fff",
          border: "1px solid #555",
          borderRadius: "4px",
          outline: "none",
          cursor: "pointer",
        }}
      >
        {roomTypeOptions.map(({ key, label }) => (
          <option key={key} value={key}>
            {label}
          </option>
        ))}
      </select>
    </div>
  );
};
