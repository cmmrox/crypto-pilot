import { useState } from "react";
import { switchEnvironment } from "../../api/client";
import { ConfirmModal, type ModalSpec } from "../../components/ConfirmModal";
import { Server } from "lucide-react";
import { Spinner } from "../../components/AsyncState";
import { useTradingStatus } from "../../trading/TradingStatus";

export function EnvironmentCard() {
  const { status, loading, refresh } = useTradingStatus();
  const env = status?.environment;
  const botRunning = status?.status !== "stopped";
  const [modal, setModal] = useState<ModalSpec | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const request = (target: string) => {
    if (!status || target === env) return;
    if (botRunning) {
      setModal({
        tone: "warning",
        kicker: "ENVIRONMENT SWITCH BLOCKED",
        title: "Stop the bot before switching accounts",
        body: "The running loop is bound to the current Binance account. Stop the bot, then switch.",
        confirmLabel: "Understood",
      });
      return;
    }
    setModal({
      tone: target === "LIVE" ? "danger" : "warning",
      kicker: "GUARDED ENVIRONMENT CHANGE",
      title: `Switch from ${env} to ${target}?`,
      body:
        target === "LIVE"
          ? "LIVE uses real funds. The next start reconciles the LIVE account. Type LIVE to confirm."
          : "DEMO uses Binance testnet funds and a separate write-only credential pair.",
      confirmWord: target === "LIVE" ? "LIVE" : undefined,
      confirmLabel: `Switch to ${target}`,
      onConfirm: async () => {
        await switchEnvironment(target, target === "LIVE" ? "LIVE" : undefined);
        setMsg(`Environment set to ${target}.`);
        await refresh();
      },
    });
  };

  return (
    <div className="panel credential-card" data-testid="environment-card">
      <div className="settings-heading">
        <span className="settings-icon">
          <Server size={18} />
        </span>
        <div>
          <p className="kicker">TRADING VENUE</p>
          <h2>Environment</h2>
          <p>DEMO and LIVE share one code path with separate write-only credentials.</p>
        </div>
        <span
          className={`pill ${env === "LIVE" ? "danger" : env === "DEMO" ? "ok" : ""}`}
          data-testid="active-env"
        >
          {loading ? (
            <>
              <Spinner size={12} /> Checking…
            </>
          ) : env ? (
            `${env} active`
          ) : (
            "Unavailable"
          )}
        </span>
      </div>
      <div className="env-options">
        <button
          className={env === "DEMO" ? "active" : ""}
          data-testid="env-demo"
          onClick={() => request("DEMO")}
          disabled={loading || !status}
        >
          <strong>DEMO / Testnet</strong>
          <small>Fake funds · safe testing</small>
        </button>
        <button
          className={`live ${env === "LIVE" ? "active" : ""}`}
          data-testid="env-live"
          onClick={() => request("LIVE")}
          disabled={loading || !status}
        >
          <strong>LIVE trading</strong>
          <small>Real funds · production</small>
        </button>
      </div>
      {msg && (
        <div className="inline-msg ok" role="status">
          {msg}
        </div>
      )}
      {modal && <ConfirmModal modal={modal} onClose={() => setModal(null)} />}
    </div>
  );
}
