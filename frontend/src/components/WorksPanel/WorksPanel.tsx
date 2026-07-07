import React from "react";
import {
  useProjectStore,
  defaultWorksForRoomType,
  type FloorWorks,
  type WallsWorks,
  type CeilingWorks,
  type ElectricWorks,
  type PlumbingWorks,
} from "../../store/projectStore";
import { allowedWorks } from "../../types/roomTypes";
import type { FloorFinish, WallFinish, CeilingFinish } from "../../types/roomTypes";
import { Select } from "../ui/Select";
import styles from "./WorksPanel.module.css";

export const WorksPanel: React.FC = () => {
  const rooms = useProjectStore((s) => s.rooms);
  const activeRoomIndex = useProjectStore((s) => s.activeRoomIndex);
  const updateRoomWorks = useProjectStore((s) => s.updateRoomWorks);

  const room = rooms[activeRoomIndex];
  if (!room) return null;

  const works = room.works ?? defaultWorksForRoomType(room.room_type);
  const allowed = allowedWorks(room.room_type);

  const setFloor = (patch: Partial<FloorWorks>) =>
    updateRoomWorks(activeRoomIndex, { floor: { ...works.floor, ...patch } });
  const setWalls = (patch: Partial<WallsWorks>) =>
    updateRoomWorks(activeRoomIndex, { walls: { ...works.walls, ...patch } });
  const setCeiling = (patch: Partial<CeilingWorks>) =>
    updateRoomWorks(activeRoomIndex, { ceiling: { ...works.ceiling, ...patch } });
  const setElectric = (patch: Partial<ElectricWorks>) =>
    updateRoomWorks(activeRoomIndex, { electric: { ...works.electric, ...patch } });
  const setPlumbing = (patch: Partial<PlumbingWorks>) =>
    updateRoomWorks(activeRoomIndex, { plumbing: { ...works.plumbing, ...patch } });

  const numInput = (
    value: number | null,
    onChange: (v: number | null) => void,
    placeholder: string,
  ) => (
    <input
      type="number"
      min={0}
      step={1}
      placeholder={placeholder}
      value={value ?? ""}
      className={styles.numInput}
      onChange={(e) => {
        const v = e.target.value === "" ? null : Number(e.target.value);
        onChange(v);
      }}
    />
  );

  return (
    <div className={styles.panel}>
      {/* Пол */}
      <div className={styles.group}>
        <label className={styles.checkRow}>
          <input
            type="checkbox"
            className={styles.check}
            checked={works.floor.enabled}
            onChange={(e) => setFloor({ enabled: e.target.checked })}
          />
          <span className={styles.groupName}>Пол</span>
        </label>
        {works.floor.enabled && (
          <div className={styles.fields}>
            <Select
              variant="box"
              ariaLabel="Отделка пола"
              value={works.floor.finish ?? allowed.floor[0]?.key ?? ""}
              options={allowed.floor.map((o) => ({ value: o.key, label: o.label }))}
              onChange={(v) => setFloor({ finish: v as FloorFinish })}
            />
          </div>
        )}
      </div>

      {/* Стены */}
      <div className={styles.group}>
        <label className={styles.checkRow}>
          <input
            type="checkbox"
            className={styles.check}
            checked={works.walls.enabled}
            onChange={(e) => setWalls({ enabled: e.target.checked })}
          />
          <span className={styles.groupName}>Стены</span>
        </label>
        {works.walls.enabled && (
          <div className={styles.fields}>
            <Select
              variant="box"
              ariaLabel="Отделка стен"
              value={works.walls.finish ?? allowed.walls[0]?.key ?? ""}
              options={allowed.walls.map((o) => ({ value: o.key, label: o.label }))}
              onChange={(v) => setWalls({ finish: v as WallFinish })}
            />
            {works.walls.finish === "wallpaper" && (
              <label className={styles.modifier}>
                <input
                  type="checkbox"
                  className={styles.check}
                  checked={works.walls.wallpaper_pattern}
                  onChange={(e) => setWalls({ wallpaper_pattern: e.target.checked })}
                />
                <span>Обои под рисунок (+30%)</span>
              </label>
            )}
            {(works.walls.finish === "paint" || works.walls.finish === "moisture_paint") && (
              <label className={styles.modifier}>
                <input
                  type="checkbox"
                  className={styles.check}
                  checked={works.walls.primer_two_coats}
                  onChange={(e) => setWalls({ primer_two_coats: e.target.checked })}
                />
                <span>Грунт в 2 слоя (пористое основание)</span>
              </label>
            )}
          </div>
        )}
      </div>

      {/* Потолок */}
      <div className={styles.group}>
        <label className={styles.checkRow}>
          <input
            type="checkbox"
            className={styles.check}
            checked={works.ceiling.enabled}
            onChange={(e) => setCeiling({ enabled: e.target.checked })}
          />
          <span className={styles.groupName}>Потолок</span>
        </label>
        {works.ceiling.enabled && (
          <div className={styles.fields}>
            <Select
              variant="box"
              ariaLabel="Отделка потолка"
              value={works.ceiling.finish ?? allowed.ceiling[0]?.key ?? ""}
              options={allowed.ceiling.map((o) => ({ value: o.key, label: o.label }))}
              onChange={(v) => setCeiling({ finish: v as CeilingFinish })}
            />
            {(works.ceiling.finish === "paint" || works.ceiling.finish === "moisture_paint") && (
              <label className={styles.modifier}>
                <input
                  type="checkbox"
                  className={styles.check}
                  checked={works.ceiling.primer_two_coats}
                  onChange={(e) => setCeiling({ primer_two_coats: e.target.checked })}
                />
                <span>Грунт в 2 слоя (пористое основание)</span>
              </label>
            )}
          </div>
        )}
      </div>

      {/* Электрика */}
      <div className={styles.group}>
        <label className={styles.checkRow}>
          <input
            type="checkbox"
            className={styles.check}
            checked={works.electric.enabled}
            onChange={(e) => setElectric({ enabled: e.target.checked })}
          />
          <span className={styles.groupName}>Электрика</span>
        </label>
        {works.electric.enabled && (
          <div className={styles.fields}>
            <div className={styles.numRow}>
              <label className={styles.numLabel}>
                Розетки
                {numInput(works.electric.sockets, (v) => setElectric({ sockets: v }), "0")}
              </label>
              <label className={styles.numLabel}>
                Светильники
                {numInput(works.electric.lights, (v) => setElectric({ lights: v }), "0")}
              </label>
              <label className={styles.numLabel}>
                Кабель, м
                {numInput(works.electric.cable_m, (v) => setElectric({ cable_m: v }), "авто")}
              </label>
            </div>
          </div>
        )}
      </div>

      {/* Сантехника */}
      <div className={styles.group}>
        <label className={styles.checkRow}>
          <input
            type="checkbox"
            className={styles.check}
            checked={works.plumbing.enabled}
            onChange={(e) => setPlumbing({ enabled: e.target.checked })}
          />
          <span className={styles.groupName}>
            Сантехника
            {allowed.plumbing.required && (
              <span className={styles.required}> · обязательно</span>
            )}
          </span>
        </label>
        {works.plumbing.enabled && (
          <div className={styles.fields}>
            <div className={styles.numRow}>
              <label className={styles.numLabel}>
                Точки подключения
                {numInput(works.plumbing.points, (v) => setPlumbing({ points: v }), "0")}
              </label>
              <label className={styles.numLabel}>
                Трубы, м
                {numInput(works.plumbing.pipe_m, (v) => setPlumbing({ pipe_m: v }), "авто")}
              </label>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
