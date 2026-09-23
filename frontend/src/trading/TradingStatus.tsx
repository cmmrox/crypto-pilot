import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { getBotStatus, type BotStatus } from "../api/client";
import { usePolling } from "../hooks/usePolling";

interface TradingStatus {
  status: BotStatus | null;
  loading: boolean;
  refresh: () => Promise<void>;
}
const Context = createContext<TradingStatus | null>(null);

/** One session-scoped source for account labels; never assume DEMO on failure. */
export function TradingStatusProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<BotStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const requestState = useRef({ generation: 0 });
  const refresh = useCallback(async () => {
    const request = ++requestState.current.generation;
    try {
      const result = await getBotStatus();
      if (result.environment !== "LIVE" && result.environment !== "DEMO") {
        throw new Error("Unrecognized trading environment");
      }
      if (request === requestState.current.generation) setStatus(result);
    } catch {
      if (request === requestState.current.generation) setStatus(null);
    } finally {
      if (request === requestState.current.generation) setLoading(false);
    }
  }, []);
  usePolling(() => void refresh(), 10000);
  useEffect(() => {
    const state = requestState.current;
    const focus = () => void refresh();
    window.addEventListener("focus", focus);
    return () => {
      ++state.generation;
      window.removeEventListener("focus", focus);
    };
  }, [refresh]);
  return <Context.Provider value={{ status, loading, refresh }}>{children}</Context.Provider>;
}

export function useTradingStatus() {
  const context = useContext(Context);
  if (!context) throw new Error("Trading status requires an authenticated provider");
  return context;
}
