import { create } from "zustand";
import type { Workspace } from "@/types";

interface AppState {
  currentWorkspace: Workspace | null;
  sidebarOpen: boolean;
  setCurrentWorkspace: (workspace: Workspace | null) => void;
  toggleSidebar: () => void;
}

export const useAppStore = create<AppState>((set) => ({
  currentWorkspace: null,
  sidebarOpen: true,
  setCurrentWorkspace: (workspace) => set({ currentWorkspace: workspace }),
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
}));
