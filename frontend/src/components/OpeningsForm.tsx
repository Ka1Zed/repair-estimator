import { useProjectStore } from "../store/projectStore";
import { Select } from "./ui/Select";

const OPENING_TYPE_OPTIONS = [
  { value: "door", label: "Дверь" },
  { value: "window", label: "Окно" },
];

export default function OpeningsForm() {
  const activeRoomIndex = useProjectStore((state) => state.activeRoomIndex);

  // 1. Исправлено: Crash guard (защита от падения при пустых комнатах)
  const openings = useProjectStore(
    (state) => state.rooms[activeRoomIndex]?.openings ?? [],
  );

  const addOpening = useProjectStore((state) => state.addOpening);
  const updateOpening = useProjectStore((state) => state.updateOpening);
  const deleteOpening = useProjectStore((state) => state.deleteOpening);

  return (
    <div
      style={{
        marginTop: "30px",
        borderTop: "1px solid #444",
        paddingTop: "20px",
      }}
    >
      <h3>Проемы (Окна и Двери)</h3>

      {openings.length > 0 && (
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
              <th style={{ paddingBottom: "10px" }}>Тип</th>
              <th style={{ paddingBottom: "10px" }}>Ширина (м)</th>
              <th style={{ paddingBottom: "10px" }}>Высота (м)</th>
              <th style={{ paddingBottom: "10px" }}>Действие</th>
            </tr>
          </thead>
          <tbody>
            {openings.map((opening, index) => (
              <tr key={opening.id}>
                <td style={{ padding: "5px 0" }}>
                  <Select
                    ariaLabel="Тип проёма"
                    value={opening.type}
                    options={OPENING_TYPE_OPTIONS}
                    onChange={(v) => updateOpening(index, "type", v)}
                  />
                </td>
                <td>
                  <input
                    type="number"
                    step="0.1"
                    min="0"
                    value={opening.width}
                    // 2. Исправлено: Проверка на отрицательные значения
                    onChange={(e) => {
                      const v = Number(e.target.value);
                      if (v >= 0) updateOpening(index, "width", v);
                    }}
                    style={{
                      width: "80px",
                      padding: "5px",
                      background: "#fff",
                      color: "var(--text-h)",
                      border: "1px solid var(--border)",
                      borderRadius: "4px",
                    }}
                  />
                </td>
                <td>
                  <input
                    type="number"
                    step="0.1"
                    min="0" // 2. Исправлено: Добавлен min="0" для высоты
                    value={opening.height}
                    // 2. Исправлено: Проверка на отрицательные значения
                    onChange={(e) => {
                      const v = Number(e.target.value);
                      if (v >= 0) updateOpening(index, "height", v);
                    }}
                    style={{
                      width: "80px",
                      padding: "5px",
                      background: "#fff",
                      color: "var(--text-h)",
                      border: "1px solid var(--border)",
                      borderRadius: "4px",
                    }}
                  />
                </td>
                <td>
                  <button
                    onClick={() => deleteOpening(index)}
                    style={{
                      padding: "5px 10px",
                      cursor: "pointer",
                      background: "#fff",
                      color: "#B5524A",
                      border: "1px solid #E3C9C4",
                      borderRadius: "3px",
                    }}
                  >
                    Удалить
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <button
        onClick={addOpening}
        style={{
          padding: "8px 15px",
          cursor: "pointer",
          background: "var(--accent)",
          color: "#fff",
          border: "none",
          borderRadius: "3px",
          fontSize: "13px",
          letterSpacing: ".01em",
        }}
      >
        + Добавить проем
      </button>
    </div>
  );
}
