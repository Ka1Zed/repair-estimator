import { create } from "zustand";

// Доступность бэкенда. Живёт отдельно от projectStore (это UI-статус сети,
// а не данные проекта). Пишут сюда health-пинг в App и любой сетевой вызов,
// который может первым упасть при мёртвом бэке (например fetchRegions).
interface BackendStatusState {
  isBackendDown: boolean;
  setBackendDown: (down: boolean) => void;
}

export const useBackendStatus = create<BackendStatusState>((set) => ({
  isBackendDown: false,
  setBackendDown: (down) => set({ isBackendDown: down }),
}));
