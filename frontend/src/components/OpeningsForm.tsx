import { useProjectStore } from "../store/projectStore";
import { Select } from "./ui/Select";
import { validateWidth, validateHeight } from "../utils/openingValidation";
import styles from "./OpeningsForm.module.css";

const OPENING_TYPE_OPTIONS = [
  { value: "door", label: "Дверь" },
  { value: "window", label: "Окно" },
];

export default function OpeningsForm() {
  const activeRoomIndex = useProjectStore((state) => state.activeRoomIndex);
  const openings = useProjectStore(
    (state) => state.rooms[activeRoomIndex]?.openings ?? [],
  );
  const ceilingHeight = useProjectStore(
    (state) => state.rooms[activeRoomIndex]?.height ?? "",
  );
  const addOpening = useProjectStore((state) => state.addOpening);
  const updateOpening = useProjectStore((state) => state.updateOpening);
  const deleteOpening = useProjectStore((state) => state.deleteOpening);

  return (
    <div className={styles.section}>
      <h3 className={styles.title}>Проемы (Окна и Двери)</h3>

      {openings.length > 0 && (
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Тип</th>
              <th>Ширина (м)</th>
              <th>Высота (м)</th>
              <th>Действие</th>
            </tr>
          </thead>
          <tbody>
            {openings.map((opening, index) => {
              const widthError = validateWidth(opening.width);
              const heightError = validateHeight(opening.height, ceilingHeight);
              return (
                <tr key={opening.id}>
                  <td>
                    <Select
                      ariaLabel="Тип проёма"
                      value={opening.type}
                      options={OPENING_TYPE_OPTIONS}
                      onChange={(v) => updateOpening(index, "type", v)}
                    />
                  </td>
                  <td>
                    <div className={styles.fieldWrap}>
                      <input
                        className={`${styles.input} ${widthError ? styles.inputError : ""}`}
                        type="number"
                        step="0.1"
                        min="0"
                        value={opening.width}
                        onChange={(e) =>
                          updateOpening(index, "width", Number(e.target.value))
                        }
                      />
                      {widthError && (
                        <span className={styles.errorText}>{widthError}</span>
                      )}
                    </div>
                  </td>
                  <td>
                    <div className={styles.fieldWrap}>
                      <input
                        className={`${styles.input} ${heightError ? styles.inputError : ""}`}
                        type="number"
                        step="0.1"
                        min="0"
                        value={opening.height}
                        onChange={(e) =>
                          updateOpening(index, "height", Number(e.target.value))
                        }
                      />
                      {heightError && (
                        <span className={styles.errorText}>{heightError}</span>
                      )}
                    </div>
                  </td>
                  <td>
                    <button
                      className={styles.deleteBtn}
                      onClick={() => deleteOpening(index)}
                    >
                      Удалить
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      <button className={styles.addBtn} onClick={addOpening}>
        + Добавить проем
      </button>
    </div>
  );
}
