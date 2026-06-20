// frontend/src/components/RepairOptionsForm/RepairOptionsForm.tsx
import React from 'react';
import { useProjectStore, type RepairType } from '../../store/projectStore';

const OPTIONS: { value: RepairType; label: string }[] = [
  { value: 'cosmetic', label: 'Косметический' },
  { value: 'basic', label: 'Капитальный' },
  { value: 'extended', label: 'Дизайнерский' },
];

export const RepairOptionsForm: React.FC = () => {
  const repairType = useProjectStore((state) => state.repair_type);
  const setRepairType = useProjectStore((state) => state.setRepairType);

  return (
    <div style={{ marginBottom: '24px' }}>
      <div
        style={{
          fontSize: '11px',
          letterSpacing: '.14em',
          textTransform: 'uppercase',
          color: '#B0B0B0',
          marginBottom: '10px',
        }}
      >
        Класс ремонта
      </div>
      <div style={{ display: 'flex', gap: '20px' }}>
        {OPTIONS.map((opt) => {
          const active = repairType === opt.value;
          return (
            <button
              key={opt.value}
              onClick={() => setRepairType(opt.value)}
              style={{
                background: 'none',
                border: 'none',
                padding: '4px 0',
                cursor: 'pointer',
                fontSize: '14px',
                letterSpacing: '.01em',
                color: active ? 'var(--text-h)' : '#9A9A9A',
                borderBottom: active ? '1.5px solid var(--accent)' : '1.5px solid transparent',
              }}
            >
              {opt.label}
            </button>
          );
        })}
      </div>
    </div>
  );
};
