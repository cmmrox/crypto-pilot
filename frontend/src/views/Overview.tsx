import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  PauseCircle,
  Play,
  ShieldAlert,
  ShieldCheck,
  Square,
  TrendingDown,
  TrendingUp,
  Wallet,
  Zap,
} from "lucide-react";
import {
  getOverview,
  killSwitch,
  startBot,
  stopBot,
  stopCloseBot,
  type Overview as OverviewData,
} from "../api/client";
import { ConfirmModal, type ModalSpec } from "../components/ConfirmModal";

const POLL_MS = 4000;

function money(v: string): string {
  const n = Number(v);
  return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function Overview() {
  const [data, setData] = useState<OverviewData | null>(null);
  const [modal, setModal] = useState<ModalSpec | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await getOverview());
    } catch {
      /* transient — keep last known */
    }
  }, []);

  useEffect(() => {
    void load();
    const t = setInterval(() => void load(), POLL_MS);
    return () => clearInterval(t);
  }, [load]);

  const showToast = (m: string) => {
    setToast(m);
    setTimeout(() => setToast(null), 4000);
  };

  const running = data?.bot_status === "running";
  const safeMode = data?.bot_status === "safe_mode";

  const act = async (fn: () => Promise<unknown>, msg: string) => {
    await fn();
    showToast(msg);
    await load();
  };

  return (
    <div className="view-stack">
      <div className="page-heading">
        <div>
          <p className="kicker">FR-02 · LIVE OPERATIONS</p>
          <h1 data-testid="view-title">Overview</h1>
          <p>Account truth from Binance · polled live</p>
        </div>
        <div className="heading-actions">
          <span
            className={`status-pill ${safeMode ? "warn" : running ? "ok" : "danger"}`}
            data-testid="bot-status"
          >
            <i className="dot" />
            {safeMode ? "Safe mode" : running ? "Bot running" : "Bot stopped"}
          </span>
          {running || safeMode ? (
            <button
              className="button secondary"
              data-testid="stop-btn"
              onClick={() =>
                setModal({
                  tone: "warning",
                  kicker: "SAFE STOP",
                  title: "Stop evaluation and leave the position open?",
                  body: "The bot stops evaluating candles. Any open position remains on Binance with its exchange stops.",
                  details: ["No new candle decisions", "Position left as-is", "SMS + audit event"],
                  confirmLabel: "Stop, leave position",
                  onConfirm: () => act(stopBot, "Bot stopped; position left as-is"),
                })
              }
            >
              <Square size={15} /> Stop bot
            </button>
          ) : (
            <button
              className="button secondary"
              data-testid="start-btn"
              onClick={() =>
                setModal({
                  tone: "warning",
                  kicker: "RECONCILE & START",
                  title: `Start on ${data?.environment ?? "DEMO"}?`,
                  body: "CryptoPilot connects to Binance, reconciles account truth, then begins the 24/7 loop.",
                  details: ["No action before reconciliation", "Mismatch → safe mode", "Decisions only at 4h close"],
                  confirmLabel: "Reconcile & start",
                  onConfirm: () => act(startBot, "Bot started; awaiting the next 4h close"),
                })
              }
            >
              <Play size={15} /> Start bot
            </button>
          )}
          <button
            className="button ghost"
            data-testid="stop-close-btn"
            onClick={() =>
              setModal({
                tone: "danger",
                kicker: "STOP & CLOSE",
                title: "Flatten the position, then stop?",
                body: "Submits a reduce-only MARKET cover, confirms the fill, then stops the loop.",
                confirmLabel: "Close position & stop",
                onConfirm: () => act(stopCloseBot, "Position flattened; bot stopped"),
              })
            }
          >
            <PauseCircle size={15} /> Stop & close
          </button>
          <button
            className="button danger"
            data-testid="kill-btn"
            onClick={() =>
              setModal({
                tone: "danger",
                kicker: `${data?.environment ?? ""} EMERGENCY CONTROL`,
                title: "Flatten everything and stop?",
                body: "Immediately cancels all orders, flattens every position at market, stops evaluation, sends SMS and writes the audit sequence.",
                confirmWord: "FLATTEN",
                confirmLabel: "Flatten & stop",
                onConfirm: () => act(killSwitch, "Kill switch activated"),
              })
            }
          >
            <Zap size={15} /> Kill switch
          </button>
        </div>
      </div>

      {safeMode && (
        <div className="banner warn" data-testid="safe-mode-banner">
          <ShieldAlert size={18} /> Safe mode — new entries are blocked; management and
          reconciliation continue.
        </div>
      )}
      {data && !data.exchange_reachable && (
        <div className="banner err">Binance unreachable — showing last known state.</div>
      )}

      <div className="stats-grid">
        <Stat label="Account balance" value={`$${money(data?.balance ?? "0")}`} icon={<Wallet size={18} />} />
        <Stat label="Total equity" value={`$${money(data?.equity ?? "0")}`} icon={<Activity size={18} />} tone="ok" />
        <Stat
          label="Unrealized P&L"
          value={`$${money(data?.unrealized_pnl ?? "0")}`}
          icon={Number(data?.unrealized_pnl ?? 0) >= 0 ? <TrendingUp size={18} /> : <TrendingDown size={18} />}
          tone={Number(data?.unrealized_pnl ?? 0) >= 0 ? "ok" : "err"}
        />
        <Stat label="Month realized" value={`$${money(data?.month_realized_pnl ?? "0")}`} icon={<TrendingUp size={18} />} />
      </div>

      <div className="overview-grid">
        <div className="panel position-panel" data-testid="position-panel">
          <p className="kicker">OPEN POSITION · LIVE BINANCE TRUTH</p>
          {data?.position ? (
            <>
              <h2>
                BTCUSDT · <span className={data.position.side === "SHORT" ? "tone-err" : "tone-ok"}>{data.position.side}</span>
              </h2>
              <div className="position-values">
                <span><small>Entry</small><strong>${money(data.position.entry_price)}</strong></span>
                <span><small>Quantity</small><strong>{data.position.qty} BTC</strong></span>
                <span><small>Effective leverage</small><strong>{data.position.leverage}×</strong></span>
                <span><small>Unrealized P&L</small><strong className={Number(data.position.unrealized_pnl) >= 0 ? "tone-ok" : "tone-err"}>${money(data.position.unrealized_pnl)}</strong></span>
              </div>
              {!data.position.has_price_stop && (
                <div className="short-risk-callout" data-testid="no-stop-callout">
                  <ShieldAlert size={19} />
                  <div>
                    <strong>No price stop — validated size-managed short</strong>
                    <p>Risk is controlled by volatility-scaled size, the independent −4% sleeve breaker, and cover only when the deep-bear regime ends on a closed 4h candle.</p>
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="empty-state"><ShieldCheck size={22} /><p>Flat — no open position.</p></div>
          )}
        </div>

        <div className="panel breaker-panel" data-testid="breaker-panel">
          <p className="kicker">INDEPENDENT GUARDRAILS</p>
          <h2>Monthly circuit breakers</h2>
          {data?.breakers.map((b) => {
            const pct = Number(b.drawdown_pct) * 100;
            const width = Math.min(100, Math.abs(pct / 4) * 100);
            return (
              <div className="breaker-item" key={b.book} data-testid={`breaker-${b.book.split(" ")[0].toLowerCase()}`}>
                <div>
                  <span>{b.book.includes("Long") ? <TrendingUp size={14} /> : <TrendingDown size={14} />}{b.book}</span>
                  <strong className={Number(b.month_to_date_pnl) >= 0 ? "tone-ok" : "tone-err"}>
                    ${money(b.month_to_date_pnl)}
                  </strong>
                </div>
                <div className="breaker-track"><i style={{ width: `${width}%` }} className={b.tripped ? "tripped" : ""} /></div>
                <small>{b.tripped ? "TRIPPED — halted until the 1st" : "Healthy · halts at −4.0% MTD"}</small>
              </div>
            );
          })}
        </div>
      </div>

      {modal && <ConfirmModal modal={modal} onClose={() => setModal(null)} />}
      {toast && (
        <div className="toast" role="status" data-testid="toast">
          <ShieldCheck size={16} /> {toast}
        </div>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  icon,
  tone,
}: {
  label: string;
  value: string;
  icon: React.ReactNode;
  tone?: "ok" | "err";
}) {
  return (
    <div className="panel stat-card">
      <div>
        <span>{label}</span>
        <strong className={tone ? `tone-${tone}` : ""}>{value}</strong>
      </div>
      <span className="icon-tile">{icon}</span>
    </div>
  );
}
