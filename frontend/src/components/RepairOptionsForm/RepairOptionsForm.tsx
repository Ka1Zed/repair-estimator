import React from 'react';
import { useProjectStore, type RepairType } from '../../store/projectStore';
import styles from './RepairOptionsForm.module.css';

const OPTIONS: { value: RepairType; label: string }[] = [
  { value: 'cosmetic', label: 'Косметический' },
  { value: 'base',     label: 'Капитальный' },
  { value: 'extended', label: 'Дизайнерский' },
];

const REPAIR_CLASS_INFO: Record<RepairType, string> = {
  cosmetic: 'Покраска, обои, замена пола. Черновые поверхности не затрагиваются.',
  base:     'Полный цикл: штукатурка, стяжка, чистовая отделка всех поверхностей.',
  extended: 'Авторский ремонт с дизайн-проектом, нестандартными материалами и повышенными нормами.',
};

export const RepairOptionsForm: React.FC = () => {
  const repairType = useProjectStore((state) => state.repair_type);
  const setRepairType = useProjectStore((state) => state.setRepairType);

  return (
    <div className={styles.section}>
      <div className={styles.label}>Класс ремонта</div>
      <div className={styles.options}>
        {OPTIONS.map((opt) => {
          const active = repairType === opt.value;
          return (
            <button
              key={opt.value}
              onClick={() => setRepairType(opt.value)}
              className={`${styles.optBtn} ${active ? styles.optBtnActive : ''}`}
            >
              {opt.label}
            </button>
          );
        })}
      </div>
      <p className={styles.description}>{REPAIR_CLASS_INFO[repairType]}</p>
    </div>
  );
};
