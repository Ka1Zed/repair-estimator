import { useProjectStore } from "../store/projectStore";

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
      alert("У помещения должно быть минимум 3 точки!");
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
    // Убрали проверку на num >= 0, теперь можно вводить минус
    if (!isNaN(num)) {
      if (field === "x") updatePoint(index, num, points[index].y);
      else updatePoint(index, points[index].x, num);
    }
  };

  return (
    <div
      style={{
        marginTop: "30px",
        borderTop: "1px solid #444",
        paddingTop: "20px",
      }}
    >
      <h3>Координаты углов (точки помещения)</h3>

      <table
        style={{
          width: "100%",
          textAlign: "left",
          borderCollapse: "collapse",
          marginBottom: "15px",
        }}
      >
        <thead>
          <tr>
            <th style={{ paddingBottom: "10px" }}>№</th>
            <th style={{ paddingBottom: "10px" }}>X (метры)</th>
            <th style={{ paddingBottom: "10px" }}>Y (метры)</th>
            <th style={{ paddingBottom: "10px" }}>Действие</th>
          </tr>
        </thead>
        <tbody>
          {points.map((point, index) => (
            <tr key={index}>
              <td style={{ padding: "5px 0" }}>{index + 1}</td>
              <td>
                <input
                  type="number"
                  step="0.1"
                  value={point.x}
                  onChange={(e) =>
                    handlePointChange(index, "x", e.target.value)
                  }
                  style={{ width: "80px", padding: "5px" }}
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
                  style={{ width: "80px", padding: "5px" }}
                />
              </td>
              <td>
                <button
                  onClick={() => handleRemovePoint(index)}
                  style={{
                    padding: "5px 10px",
                    cursor: "pointer",
                    background: "#551111",
                    color: "white",
                    border: "none",
                    borderRadius: "4px",
                  }}
                >
                  Удалить
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <button
        onClick={handleAddPoint}
        style={{
          padding: "8px 15px",
          cursor: "pointer",
          background: "#225522",
          color: "white",
          border: "none",
          borderRadius: "4px",
        }}
      >
        + Добавить точку
      </button>
    </div>
  );
}
