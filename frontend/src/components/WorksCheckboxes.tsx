import React from 'react';
import { useProjectStore } from '../store/projectStore';
import { roomTypes } from '../types/roomTypes';

export const WorksCheckboxes: React.FC = () => {
  const { rooms, activeRoomIndex, updateRepairOptions } = useProjectStore();
  const room = rooms[activeRoomIndex];
  
  if (!room) return null;

  const repairOptions = room.repair_options || { 
    floor: false, walls: false, ceiling: false, tile: false, electric: false, plumbing: false 
  };
  const labelsMap: Record<string, string> = {
  floor: "Пол",
  walls: "Стены",
  ceiling: "Потолок",
  tile: "Плитка",
  electric: "Электрика",
  plumbing: "Сантехника"
};

  const handleToggle = (key: keyof typeof repairOptions) => {
    updateRepairOptions(activeRoomIndex, { [key]: !repairOptions[key] });
  };

  // Получаем правила для текущего типа комнаты из матрицы
  const currentRoomRules = roomTypes[room.room_type as keyof typeof roomTypes];

  return (
    <div className="works-checkboxes">
      {Object.keys(repairOptions).map((key) => {
        // Логика блокировки по ТЗ:
        // Например, плитка (tile) блокируется, если в матрице tile: false
        const isBlocked = (key === 'tile' && !currentRoomRules.tile) || 
                          (key === 'plumbing' && !currentRoomRules.plumbing.available);

        return (
            
          <label key={key} style={{ display: 'flex', alignItems: 'center', marginBottom: '8px' }}>
            <input
            
                type="checkbox"
                checked={!!repairOptions[key as keyof typeof repairOptions]}
                onChange={() => handleToggle(key as keyof typeof repairOptions)}
                disabled={isBlocked}
                style={{ marginRight: '8px' }} // отступ между чекбоксом и текстом
            />
           <span style={{ fontSize: '14px', color: '#333' }}>
            {labelsMap[key] || key.charAt(0).toUpperCase() + key.slice(1)}
            </span>
    </label>
        );
      })}
    </div>
  );
};