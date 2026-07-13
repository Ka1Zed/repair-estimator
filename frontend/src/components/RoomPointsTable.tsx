import { useProjectStore } from "../store/projectStore";
import styles from "./RoomPointsTable.module.css";

export default function RoomPointsTable() {
  const activeRoomIndex = useProjectStore((state) => state.activeRoomIndex);
  const points = useProjectStore(
    (state) => state.rooms[activeRoomIndex].points,
  );

  const setPoints = useProjectStore((state) => state.setPoints);
  const updatePoint = useProjectStore((state) => state.updatePoint);

  const handleAddPoint = () => {
    setPoints([...points, { x: 0, y: 0 }]);
  };

  const handleRemovePoint = (indexToRemove: number) => {
    if (points.length <= 3) {
      alert("У комнаты должно быть минимум 3 точки!");
      return;
    }
    setPoints(points.filter((_, index) => index !== indexToRemove));
  };

  const handlePointChange = (
    index: number,
    field: "x" | "y",
    value: string,
  ) => {
    if (value === "") {
      if (field === "x") updatePoint(index, "", points[index].y);
      else updatePoint(index, points[index].x, "");
      return;
    }

    const num = Number(value);
    if (!isNaN(num)) {
      if (field === "x") updatePoint(index, num, points[index].y);
      else updatePoint(index, points[index].x, num);
    }
  };

  return (
    <div className={styles.wrapper}>
      <h3>Координаты углов (точки комнаты)</h3>

      <table className={styles.table}>
        <thead>
          <tr>
            <th className={styles.th}>№</th>
            <th className={styles.th}>X (метры)</th>
            <th className={styles.th}>Y (метры)</th>
            <th className={styles.th}>Действие</th>
          </tr>
        </thead>
        <tbody>
          {points.map((point, index) => (
            <tr key={index}>
              <td className={styles.td}>{index + 1}</td>
              <td>
                <input
                  type="number"
                  step="0.1"
                  value={point.x}
                  onChange={(e) =>
                    handlePointChange(index, "x", e.target.value)
                  }
                  className={styles.input}
                />
              </td>
              <td>
                <input
                  type="number"
                  step="0.1"
                  value={point.y}
                  onChange={(e) =>
                    handlePointChange(index, "y", e.target.value)
                  }
                  className={styles.input}
                />
              </td>
              <td>
                <button
                  onClick={() => handleRemovePoint(index)}
                  className={styles.deleteBtn}
                >
                  Удалить
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <button onClick={handleAddPoint} className={styles.addBtn}>
        + Добавить точку
      </button>
    </div>
  );
}
