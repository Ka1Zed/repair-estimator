import { useProjectStore } from "../store/projectStore";
import styles from "./RoomsList.module.css";

export default function RoomsList() {
  const rooms = useProjectStore((state) => state.rooms);
  const activeRoomIndex = useProjectStore((state) => state.activeRoomIndex);

  const setActiveRoom = useProjectStore((state) => state.setActiveRoom);
  const addRoom = useProjectStore((state) => state.addRoom);
  const deleteRoom = useProjectStore((state) => state.deleteRoom);
  const updateRoomName = useProjectStore((state) => state.updateRoomName);

  return (
    <div className={styles.list}>
      {rooms.map((room, index) => {
        const active = activeRoomIndex === index;
        return (
          <div
            key={room.id}
            onClick={() => setActiveRoom(index)}
            className={`${styles.room} ${active ? styles.roomActive : ""}`}
          >
            <input
              type="text"
              value={room.name}
              placeholder="Например: Спальня, Сарай, Мастерская"
              onChange={(e) => updateRoomName(index, e.target.value)}
              onClick={(e) => {
                e.stopPropagation();
                setActiveRoom(index);
              }}
              className={`${styles.nameInput} ${active ? styles.nameInputActive : ""}`}
              style={{ width: Math.max(64, room.name.length * 8) }}
            />

            {rooms.length > 1 && (
              <span
                onClick={(e) => {
                  e.stopPropagation();
                  deleteRoom(index);
                }}
                className={styles.deleteBtn}
              >
                ×
              </span>
            )}
          </div>
        );
      })}

      <button onClick={addRoom} className={styles.addBtn}>
        + комната
      </button>
    </div>
  );
}
