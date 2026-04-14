import { create } from 'zustand';

interface UIState {
  isDrawerOpen: boolean;
  activeCitationId: string | null;
  openCitationContext: (id: string) => void;
  closeDrawer: () => void;
}

export const useUIStore = create<UIState>((set) => ({
  isDrawerOpen: false,
  activeCitationId: null,
  openCitationContext: (id) => set({ isDrawerOpen: true, activeCitationId: id }),
  closeDrawer: () => set({ isDrawerOpen: false, activeCitationId: null }),
}));
