import { useProjectStore } from "../store/projectStore";
import { roomTypeOptions, type RoomTypeKey } from "../types/roomTypes";
import styles from "./RoomTypeSelector.module.css";
import { WorksCheckboxes } from "./WorksCheckboxes";

export const RoomTypeSelector = () => {
  const activeRoomIndex = useProjectStore((state) => state.activeRoomIndex);
  const rooms = useProjectStore((state) => state.rooms);
  const updateActiveRoomType = useProjectStore(
    (state) => state.updateActiveRoomType,
  );

  const activeRoom = rooms[activeRoomIndex];

  if (!activeRoom) return null;

  return (
    <div className={styles.container}>
      <label htmlFor="room-type" className={styles.label}>
        Тип комнаты:
      </label>
      <select
        id="room-type"
        value={activeRoom.room_type}
        onChange={(e) => updateActiveRoomType(activeRoomIndex, e.target.value as RoomTypeKey)}
        className={styles.select}
      >
        {roomTypeOptions.map(({ key, label }) => (
          <option key={key} value={key}>
            {label}
          </option>
        ))}
      </select>
      <WorksCheckboxes />
    </div>
  );
};
