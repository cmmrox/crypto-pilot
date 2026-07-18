import { create } from "zustand";
import {
  clearTokens,
  getMe,
  hasSession,
  logout as apiLogout,
  setUnauthorizedHandler,
  type Me,
} from "../api/client";

type AuthStatus = "loading" | "authenticated" | "unauthenticated";

interface AuthState {
  status: AuthStatus;
  user: Me | null;
  /** Called on app boot: if a session exists, verify it against /me. */
  bootstrap: () => Promise<void>;
  setAuthenticated: (user: Me) => void;
  signOut: () => Promise<void>;
  /** Invoked when the API layer determines the session is dead. */
  forceUnauthenticated: () => void;
}

export const useAuth = create<AuthState>((set) => ({
  status: "loading",
  user: null,
  bootstrap: async () => {
    // Wire the API layer so a dead session drops the UI to login.
    setUnauthorizedHandler(() => set({ status: "unauthenticated", user: null }));
    if (!hasSession()) {
      set({ status: "unauthenticated", user: null });
      return;
    }
    try {
      const user = await getMe();
      set({ status: "authenticated", user });
    } catch {
      clearTokens();
      set({ status: "unauthenticated", user: null });
    }
  },
  setAuthenticated: (user) => set({ status: "authenticated", user }),
  signOut: async () => {
    await apiLogout();
    set({ status: "unauthenticated", user: null });
  },
  forceUnauthenticated: () => {
    clearTokens();
    set({ status: "unauthenticated", user: null });
  },
}));
