import { useProjectStore } from "../store/projectStore";

export default function OpeningsForm() {
  const activeRoomIndex = useProjectStore((state) => state.activeRoomIndex);
  const openings = useProjectStore(
    (state) => state.rooms[activeRoomIndex].openings,
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
                  <select
                    value={opening.type}
                    onChange={(e) =>
                      updateOpening(index, "type", e.target.value)
                    }
                    style={{
                      padding: "5px",
                      background: "#333",
                      color: "#fff",
                      border: "1px solid #555",
                      borderRadius: "4px",
                    }}
                  >
                    <option value="door">Дверь</option>
                    <option value="window">Окно</option>
                  </select>
                </td>
                <td>
                  <input
                    type="number"
                    step="0.1"
                    min="0"
                    value={opening.width}
                    onChange={(e) =>
                      updateOpening(
                        index,
                        "width",
                        e.target.value === "" ? "" : Number(e.target.value),
                      )
                    }
                    style={{
                      width: "80px",
                      padding: "5px",
                      background: "#333",
                      color: "#fff",
                      border: "1px solid #555",
                      borderRadius: "4px",
                    }}
                  />
                </td>
                <td>
                  <input
                    type="number"
                    step="0.1"
                    min="0"
                    value={opening.height}
                    onChange={(e) =>
                      updateOpening(
                        index,
                        "height",
                        e.target.value === "" ? "" : Number(e.target.value),
                      )
                    }
                    style={{
                      width: "80px",
                      padding: "5px",
                      background: "#333",
                      color: "#fff",
                      border: "1px solid #555",
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
      )}

      <button
        onClick={addOpening}
        style={{
          padding: "8px 15px",
          cursor: "pointer",
          background: "#4a90e2",
          color: "white",
          border: "none",
          borderRadius: "4px",
        }}
      >
        + Добавить проем
      </button>
    </div>
  );
}
