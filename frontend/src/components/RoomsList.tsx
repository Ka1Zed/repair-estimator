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
        padding: "20px",
        background: "#222",
        borderRadius: "8px",
        width: "100%",
        maxWidth: "250px",
        color: "#fff",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "15px",
        }}
      >
        <h3 style={{ margin: 0 }}>Помещения</h3>
        <button
          onClick={addRoom}
          style={{
            background: "#5cba5c",
            color: "#fff",
            border: "none",
            padding: "6px 12px",
            borderRadius: "4px",
            cursor: "pointer",
            fontWeight: "bold",
          }}
        >
          + Добавить
        </button>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
        {rooms.map((room, index) => {
          const isActive = activeRoomIndex === index;
          return (
            <div
              key={room.id}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "10px",
                padding: "10px",
                background: isActive ? "#333" : "#1a1a1a",
                border: isActive
                  ? "2px solid #5cba5c"
                  : "2px solid transparent",
                borderRadius: "6px",
                cursor: "pointer",
                transition: "all 0.2s",
              }}
              onClick={() => setActiveRoom(index)}
            >
              <div style={{ flexGrow: 1 }}>
                <input
                  type="text"
                  value={room.name}
                  onChange={(e) => updateRoomName(index, e.target.value)}
                  // ИСПРАВЛЕНО: теперь при клике на текст мы тоже принудительно активируем эту комнату
                  onClick={(e) => {
                    e.stopPropagation();
                    setActiveRoom(index);
                  }}
                  style={{
                    background: "transparent",
                    border: "none",
                    borderBottom: isActive
                      ? "1px solid #555"
                      : "1px solid transparent",
                    color: "#fff",
                    fontSize: "15px",
                    outline: "none",
                    width: "100%",
                    paddingBottom: "2px",
                    cursor: "pointer",
                  }}
                />
              </div>

              {rooms.length > 1 && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    deleteRoom(index);
                  }}
                  style={{
                    background: "transparent",
                    color: "#ba5c5c",
                    border: "1px solid #ba5c5c",
                    padding: "4px 8px",
                    borderRadius: "4px",
                    cursor: "pointer",
                    fontSize: "12px",
                  }}
                >
                  Удалить
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
