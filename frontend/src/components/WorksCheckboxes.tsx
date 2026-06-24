import React from 'react';
import { useProjectStore, type RepairOptions } from '../store/projectStore';
import { roomTypes, type RoomTypeKey } from '../types/roomTypes';

const BOOLEAN_KEYS = new Set<keyof RepairOptions>(['tile', 'plumbing']);

const labelsMap: Record<string, string> = {
  floor: 'Пол',
  walls: 'Стены',
  ceiling: 'Потолок',
  tile: 'Плитка',
  electric: 'Электрика',
  plumbing: 'Сантехника',
};

export const WorksCheckboxes: React.FC = () => {
  const { rooms, activeRoomIndex, repair_options: repairOptions, updateRepairOptions } = useProjectStore();
  const room = rooms[activeRoomIndex];

  if (!room) return null;

  const rules = roomTypes[room.room_type as RoomTypeKey];

  const handleToggle = (key: keyof RepairOptions) => {
    if (BOOLEAN_KEYS.has(key)) {
      updateRepairOptions({ [key]: !repairOptions[key] });
      return;
    }
    if (repairOptions[key]) {
      updateRepairOptions({ [key]: null });
    } else {
      const options = rules?.[key as 'floor' | 'walls' | 'ceiling' | 'electric'];
      const first = Array.isArray(options) ? options[0] ?? null : null;
      updateRepairOptions({ [key]: first });
    }
  };

  return (
    <div className="works-checkboxes">
      {(Object.keys(labelsMap) as (keyof RepairOptions)[]).map((key) => {
        const isBlocked =
          (key === 'tile' && !rules?.tile) ||
          (key === 'plumbing' && !rules?.plumbing.available);

        return (
          <label
            key={key}
            style={{
              display: 'flex',
              alignItems: 'center',
              marginBottom: '10px',
              cursor: isBlocked ? 'default' : 'pointer',
              opacity: isBlocked ? 0.4 : 1,
            }}
          >
            <input
              type="checkbox"
              checked={!!repairOptions[key]}
              onChange={() => handleToggle(key)}
              disabled={isBlocked}
              style={{
                width: '16px',
                height: '16px',
                marginRight: '10px',
                accentColor: 'var(--accent)',
                cursor: isBlocked ? 'default' : 'pointer',
              }}
            />
            <span style={{ fontSize: '14px', color: 'var(--text-h)' }}>{labelsMap[key]}</span>
          </label>
        );
      })}
    </div>
  );
};
