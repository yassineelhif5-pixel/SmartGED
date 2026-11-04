import { create } from "zustand";
import type { Session } from "@/types/api";

interface SessionState {
  session: Session | null;
  ready: boolean;
  setSession: (s: Session | null) => void;
  markReady: () => void;
}

export const useSessionStore = create<SessionState>((set) => ({
  session: null,
  ready: false,
  setSession: (session) => set({ session }),
  markReady: () => set({ ready: true }),
}));

/** Permission check helper — UI only; the backend always re-checks. */
export function useCan() {
  const perms = useSessionStore((s) => s.session?.permissions);
  return (p: string) => !!perms?.includes(p);
}

type Theme = "light" | "dark" | "system";

interface UiState {
  theme: Theme;
  sidebarCollapsed: boolean;
  setTheme: (t: Theme) => void;
  toggleSidebar: () => void;
}

const storedTheme = (() => {
  try {
    return (localStorage.getItem("documind-theme") as Theme) || "system";
  } catch {
    return "system" as Theme;
  }
})();

export function applyTheme(theme: Theme) {
  const dark = theme === "dark" || (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
}

export const useUiStore = create<UiState>((set) => ({
  theme: storedTheme,
  sidebarCollapsed: false,
  setTheme: (theme) => {
    try {
      localStorage.setItem("documind-theme", theme);
    } catch {
      /* storage unavailable */
    }
    applyTheme(theme);
    set({ theme });
  },
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
}));
