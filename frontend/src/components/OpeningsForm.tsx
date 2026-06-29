import { useProjectStore } from "../store/projectStore";
import { Select } from "./ui/Select";
import styles from "./OpeningsForm.module.css";

const OPENING_TYPE_OPTIONS = [
  { value: "door", label: "Дверь" },
  { value: "window", label: "Окно" },
];

function validateWidth(width: number | string): string | null {
  const v = Number(width);
  if (!width && width !== 0) return null;
  if (isNaN(v) || v <= 0) return "Должна быть > 0";
  if (v > 10) return "Не более 10 м";
  return null;
}

function validateHeight(
  height: number | string,
  ceilingHeight: number | string,
): string | null {
  const v = Number(height);
  const ceiling = Number(ceilingHeight);
  if (!height && height !== 0) return null;
  if (isNaN(v) || v <= 0) return "Должна быть > 0";
  if (ceiling > 0 && v > ceiling) return `Не более ${ceiling} м (потолок)`;
  return null;
}

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
                        onChange={(e) => {
                          const v = Number(e.target.value);
                          if (v >= 0) updateOpening(index, "width", v);
                        }}
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
                        onChange={(e) => {
                          const v = Number(e.target.value);
                          if (v >= 0) updateOpening(index, "height", v);
                        }}
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
