import { useProjectStore } from "../store/projectStore";
import { roomTypeOptions, type RoomTypeKey } from "../types/roomTypes";
import styles from "./RoomTypeSelector.module.css";
import { WorksCheckboxes } from "./WorksCheckboxes";
import { Select } from "./ui/Select";

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
      <Select
        id="room-type"
        fullWidth
        ariaLabel="Тип комнаты"
        value={activeRoom.room_type}
        options={roomTypeOptions.map(({ key, label }) => ({ value: key, label }))}
        onChange={(v) => updateActiveRoomType(activeRoomIndex, v as RoomTypeKey)}
      />
      <WorksCheckboxes />
    </div>
  );
};
