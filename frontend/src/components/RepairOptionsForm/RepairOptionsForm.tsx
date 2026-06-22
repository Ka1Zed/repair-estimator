// frontend/src/components/RepairOptionsForm/RepairOptionsForm.tsx
import React from 'react';
import { useProjectStore, type RepairType } from '../../store/projectStore';

export const RepairOptionsForm: React.FC = () => {
  // Достаем текущее значение и функцию обновления из стора
  const repairType = useProjectStore((state) => state.repair_type);
  const setRepairType = useProjectStore((state) => state.setRepairType);

  // Обработчик изменения выбора
  const handleChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setRepairType(event.target.value as RepairType);
  };

  return (
    <div className="repair-options-form">
      <h3>Класс ремонта</h3>
      <div className="options-container">
        <label>
          <input
            type="radio"
            name="repair_type"
            value="cosmetic"
            checked={repairType === 'cosmetic'}
            onChange={handleChange}
          />
          Косметический
        </label>

        <label>
          <input
            type="radio"
            name="repair_type"
            value="base"
            checked={repairType === 'base'}
            onChange={handleChange}
          />
          Базовый
        </label>

        <label>
          <input
            type="radio"
            name="repair_type"
            value="extended"
            checked={repairType === 'extended'}
            onChange={handleChange}
          />
          Расширенный
        </label>
      </div>
    </div>
  );
};