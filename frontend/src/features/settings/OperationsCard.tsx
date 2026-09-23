import { useState } from "react";
import { Activity, Database, RadioTower, RefreshCw, Wifi } from "lucide-react";
import { getDeepHealth, type DeepHealth } from "../../api/client";
import { LoadingState, Spinner } from "../../components/AsyncState";
import { usePolling } from "../../hooks/usePolling";

export function OperationsCard() {
  const [h, setH] = useState<DeepHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const load = async () => {
    setLoading(true);
    try {
      setH(await getDeepHealth());
    } catch {
      setH(null);
    } finally {
      setLoading(false);
    }
  };
  usePolling(() => void load(), 10000);
  const tick = h?.ingest_last_tick ? h.ingest_last_tick.slice(11, 19) + " UTC" : "—";
  return (
    <div className="panel" data-testid="operations-card">
      <div className="settings-heading">
        <span className="settings-icon">
          <Activity size={18} />
        </span>
        <div>
          <p className="kicker">RELIABILITY</p>
          <h2>Operations & health</h2>
          <p>Live service health, scheduler heartbeat and the dead-man's switch.</p>
        </div>
        <span className={`pill ${h?.status === "ok" ? "ok" : "warn"}`} data-testid="ops-status">
          {loading && !h ? (
            <>
              <Spinner size={12} /> Checking…
            </>
          ) : h?.status === "ok" ? (
            "All healthy"
          ) : (
            "Degraded"
          )}
        </span>
      </div>
      {loading && !h ? (
        <LoadingState
          compact
          title="Running service health checks…"
          detail="Checking the database, scheduler, ingest loop, and dead-man switch."
        />
      ) : (
        <div className="operations-grid">
          <span>
            <Database size={16} />
            <div>
              <small>Database</small>
              <strong>{h?.database ?? "—"}</strong>
            </div>
          </span>
          <span>
            <RadioTower size={16} />
            <div>
              <small>Scheduler</small>
              <strong>{h?.scheduler_alive ? "Alive" : "Down"}</strong>
            </div>
          </span>
          <span>
            <Wifi size={16} />
            <div>
              <small>Last candle tick</small>
              <strong>{tick}</strong>
            </div>
          </span>
          <span>
            <Activity size={16} />
            <div>
              <small>Dead-man switch</small>
              <strong>{h?.ingest_overdue ? "OVERDUE" : "Armed"}</strong>
            </div>
          </span>
        </div>
      )}
      <button
        className="button secondary"
        data-testid="ops-refresh"
        onClick={() => void load()}
        disabled={loading}
      >
        {loading ? (
          <>
            <Spinner /> Running health check…
          </>
        ) : (
          <>
            <RefreshCw size={14} /> Run health check
          </>
        )}
      </button>
    </div>
  );
}
