import { useProjectStore } from "../../store/projectStore";
import { roomTypesMatrix, type RoomTypeConfig } from "../../roomTypes";

export function WorksCheckboxes() {
  const activeRoomIndex = useProjectStore((state) => state.activeRoomIndex);
  const rooms = useProjectStore((state) => state.rooms);
  const updateRepairOptions = useProjectStore((state) => state.updateRepairOptions);

  const activeRoom = rooms[activeRoomIndex];
  
  const roomType = roomTypesMatrix[activeRoom.room_type] ? activeRoom.room_type : "living";
  const matrix = roomTypesMatrix[roomType];
  const options = activeRoom.repair_options || {};

  const handleCheck = (field: keyof RoomTypeConfig, isChecked: boolean) => {
    let value: string | boolean = isChecked;
    const matrixValue = matrix[field];

    if (isChecked && Array.isArray(matrixValue)) {
      value = matrixValue[0];
    }

    updateRepairOptions(activeRoomIndex, { [field]: value });
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '16px' }}>
      <h4>Необходимые работы</h4>

      <label>
        <input
          type="checkbox"
          checked={!!options.floor}
          disabled={!matrix.floor || matrix.floor.length === 0}
          onChange={(e) => handleCheck("floor", e.target.checked)}
        />
        Пол
      </label>

      <label>
        <input
          type="checkbox"
          checked={!!options.walls}
          disabled={!matrix.walls || matrix.walls.length === 0}
          onChange={(e) => handleCheck("walls", e.target.checked)}
        />
        Стены
      </label>

      <label>
        <input
          type="checkbox"
          checked={!!options.ceiling}
          disabled={!matrix.ceiling || matrix.ceiling.length === 0}
          onChange={(e) => handleCheck("ceiling", e.target.checked)}
        />
        Потолок
      </label>

      <label>
        <input
          type="checkbox"
          checked={!!options.tile}
          disabled={matrix.tile === false}
          onChange={(e) => handleCheck("tile", e.target.checked)}
        />
        Плитка
      </label>

      <label>
        <input
          type="checkbox"
          checked={!!options.electric}
          disabled={!matrix.electric || matrix.electric.length === 0}
          onChange={(e) => handleCheck("electric", e.target.checked)}
        />
        Электрика
      </label>

      <label>
        <input
          type="checkbox"
          checked={!!options.plumbing}
          disabled={!matrix.plumbing?.available}
          onChange={(e) => handleCheck("plumbing", e.target.checked)}
        />
        Сантехника
      </label>
    </div>
  );
}