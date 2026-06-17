import { create } from 'zustand';

// Описываем типы для ремонта (как указано в Issue #90)
export type RepairType = 'cosmetic' | 'basic' | 'extended';

// Описываем интерфейс всего состояния нашего проекта
interface ProjectState {
  repair_type: RepairType;
  setRepairType: (type: RepairType) => void;
  
  // В будущем твои коллеги добавят сюда комнаты, точки и т.д.
}

// Создаем сам стор
export const useProjectStore = create<ProjectState>((set) => ({
  repair_type: 'cosmetic', // Значение по умолчанию из задачи
  setRepairType: (type) => set({ repair_type: type }),
}));