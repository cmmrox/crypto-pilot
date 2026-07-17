import { useEffect, useState } from "react";
import { getHealth, type Health } from "./api/client";

/**
 * Stage 0 walking skeleton. Confirms the frontend builds, is served by Caddy,
 * and can reach the backend /health endpoint through the reverse proxy.
 * Real screens (Login, Overview, ...) arrive in Stage 1+.
 */
export function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "unknown error"));
  }, []);

  return (
    <main className="skeleton">
      <div className="brand">
        <span className="dot" />
        <h1>CryptoPilot</h1>
      </div>
      <p className="tagline">Automated BTCUSDT trading control room</p>
      <section className="status-card" data-testid="health-card">
        <h2>System status</h2>
        {error && (
          <p className="status error" data-testid="health-status">
            Backend unreachable: {error}
          </p>
        )}
        {!error && !health && (
          <p className="status" data-testid="health-status">
            Checking…
          </p>
        )}
        {health && (
          <ul>
            <li data-testid="health-status">
              Status: <strong className={health.status === "ok" ? "ok" : "warn"}>{health.status}</strong>
            </li>
            <li>Database: <strong>{health.database}</strong></li>
            <li>Version: <strong>{health.version}</strong></li>
          </ul>
        )}
      </section>
      <footer>Stage 0 — foundations. Screens land in the next stages.</footer>
    </main>
  );
}
