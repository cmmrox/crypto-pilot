import { useEffect, useState } from "react";
import { CheckCircle2, Waypoints } from "lucide-react";
import { getStrategies, switchStrategy, type StrategyInfo } from "../../api/client";
import { ConfirmModal, type ModalSpec } from "../../components/ConfirmModal";
import { LoadingState } from "../../components/AsyncState";

export function StrategyLibrary() {
  const [strategies, setStrategies] = useState<StrategyInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [modal, setModal] = useState<ModalSpec | null>(null);
  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      setStrategies(await getStrategies());
    } catch {
      setStrategies([]);
      setError(
        "Strategy releases could not be loaded. Retry to confirm the current active release.",
      );
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    void load();
  }, []);
  const selectStrategy = (strategy: StrategyInfo) =>
    setModal({
      tone: "warning",
      kicker: "VALIDATED RELEASE CHANGE",
      title: `Select ${strategy.display_name}?`,
      body: "Audit-logged; requires a stopped bot and no open position. Applies at the next reconciled start; does not start trading or change DEMO/LIVE mode.",
      details: [strategy.summary, ...strategy.caveats],
      confirmLabel: "Select release",
      onConfirm: async () => {
        await switchStrategy(strategy.name);
        await load();
        window.dispatchEvent(new Event("strategy-changed"));
      },
    });
  return (
    <div className="panel" data-testid="strategy-library">
      <div className="settings-heading">
        <span className="settings-icon">
          <Waypoints size={18} />
        </span>
        <div>
          <p className="kicker">REGISTERED PLUGINS</p>
          <h2>Strategy library</h2>
          <p>Deployed configuration is read-only; changes ship as validated releases.</p>
        </div>
      </div>
      <div className="strategy-list">
        {error && (
          <div role="alert">
            <p>{error}</p>
            <button className="button ghost" onClick={() => void load()}>
              Retry
            </button>
          </div>
        )}
        {loading && strategies.length === 0 && (
          <LoadingState
            compact
            title="Loading strategy releases…"
            detail="Reading the deployed, parity-validated plugin manifest."
          />
        )}
        {strategies.map((s) => (
          <article
            key={s.name}
            className={s.active ? "active" : ""}
            data-testid={`strategy-${s.name}`}
          >
            <div>
              <strong>{s.display_name}</strong>
              <code>
                {s.name} · release {s.validated_release}
              </code>
              <p>{s.summary}</p>
              <small>
                {s.symbol} · {s.interval} · {s.decision_point.replace("_", " ")}
              </small>
            </div>
            <span className="strategy-dir">{s.direction}</span>
            <details>
              <summary>How this strategy works</summary>
              <p>{s.description}</p>
              <h4>Entries</h4>
              <ul>
                {s.entries.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
              <h4>Exits</h4>
              <ul>
                {s.exits.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
              <h4>Risk controls</h4>
              <ul>
                {s.risk_controls.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
              <h4>Caveats</h4>
              <ul>
                {s.caveats.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
              <h4>Read-only release parameters</h4>
              <ul data-testid={`parameters-${s.name}`}>
                {Object.entries(s.params).map(([key, value]) => (
                  <li key={key}>
                    {key.replaceAll("_", " ")}: <strong>{value}</strong>
                  </li>
                ))}
              </ul>
              <small>
                Warm-up {s.warmup_bars} bars · history {s.history_bars} bars · validation:{" "}
                {s.validation_method}
              </small>
            </details>
            <div className="strategy-badges">
              {s.parity_verified && (
                <span className="pill ok" data-testid={`parity-${s.name}`}>
                  <CheckCircle2 size={12} /> Parity verified
                </span>
              )}
              <span className={`pill ${s.active ? "ok" : "warn"}`}>
                {s.active ? "Active" : "Inactive"}
              </span>
              {!s.active && (
                <button
                  className="button ghost small"
                  data-testid={`select-${s.name}`}
                  onClick={() => selectStrategy(s)}
                >
                  Select
                </button>
              )}
            </div>
          </article>
        ))}
      </div>
      {modal && <ConfirmModal modal={modal} onClose={() => setModal(null)} />}
    </div>
  );
}
