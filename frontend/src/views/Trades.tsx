import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronRight, Download, RotateCcw, Search, X } from "lucide-react";
import {
  getTradeDetail,
  getTrades,
  getTradesCsv,
  getStrategies,
  type StrategyInfo,
  type TradeDetail,
  type TradeFilters,
  type TradeRow,
} from "../api/client";

export function Trades() {
  const [rows, setRows] = useState<TradeRow[]>([]);
  const [filters, setFilters] = useState<TradeFilters>({});
  const [selected, setSelected] = useState<TradeDetail | null>(null);
  const [strategies, setStrategies] = useState<StrategyInfo[]>([]);
  const loadSeq = useRef(0);

  const load = useCallback(async () => {
    const seq = ++loadSeq.current;
    try {
      const result = await getTrades(filters);
      if (seq === loadSeq.current) setRows(result); // ignore out-of-order responses
    } catch {
      if (seq === loadSeq.current) setRows([]);
    }
  }, [filters]);

  useEffect(() => {
    void load();
  }, [load]);
  useEffect(() => {
    getStrategies().then(setStrategies).catch(() => setStrategies([]));
  }, []);

  const setF = (k: keyof TradeFilters, v: string) => setFilters((f) => ({ ...f, [k]: v }));
  const reset = () => setFilters({});

  const exportCsv = async () => {
    const text = await getTradesCsv(filters).catch(() => "");
    const blob = new Blob([text], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "cryptopilot-trades.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="view-stack">
      <div className="page-heading">
        <div>
          <p className="kicker">FR-07 · RECONCILED HISTORY</p>
          <h1 data-testid="view-title">Trades</h1>
          <p>Every round trip, order and fill — reconciled to Binance.</p>
        </div>
        <button className="button secondary" data-testid="export-csv" onClick={() => void exportCsv()}>
          <Download size={15} /> Export CSV
        </button>
      </div>

      <div className="toolbar">
        <label className="search-field">
          <Search size={15} />
          <input
            aria-label="Search trades"
            placeholder="Search exit reason or trade id"
            value={filters.search ?? ""}
            onChange={(e) => setF("search", e.target.value)}
          />
        </label>
        <select aria-label="Filter by side" value={filters.side ?? ""} onChange={(e) => setF("side", e.target.value)}>
          <option value="">All sides</option>
          <option>LONG</option>
          <option>SHORT</option>
        </select>
        <select
          aria-label="Filter by environment"
          value={filters.environment ?? ""}
          onChange={(e) => setF("environment", e.target.value)}
        >
          <option value="">All environments</option>
          <option>DEMO</option>
          <option>LIVE</option>
        </select>
        <select
          aria-label="Filter by strategy"
          value={filters.strategy ?? ""}
          onChange={(e) => setF("strategy", e.target.value)}
        >
          <option value="">All strategies</option>
          {strategies.map((strategy) => (
            <option key={strategy.name} value={strategy.name}>
              {strategy.display_name}
            </option>
          ))}
        </select>
        <input
          aria-label="Filter by month"
          type="month"
          value={filters.month ?? ""}
          onChange={(e) => setF("month", e.target.value)}
        />
        <button className="button ghost" onClick={reset}>
          <RotateCcw size={14} /> Reset
        </button>
        <span className="result-count">{rows.length} trades</span>
      </div>

      <div className="events-panel" data-testid="trades-table">
        <div className="trade-head">
          <span>Trade</span>
          <span>Opened</span>
          <span>Side</span>
          <span>Strategy</span>
          <span>Entry / exit</span>
          <span>Realized</span>
          <span>Reason</span>
        </div>
        {rows.length === 0 && (
          <div className="empty-state">
            <Search size={24} />
            <p>No matching trades.</p>
          </div>
        )}
        {rows.map((t) => (
          <button
            key={t.id}
            className="trade-row"
            onClick={() => void getTradeDetail(t.id).then(setSelected)}
            aria-label={`Trade ${t.id} detail`}
          >
            <span>
              <strong>#{t.id}</strong>
              <em className={`outcome ${t.outcome.toLowerCase()}`}>{t.outcome}</em>
            </span>
            <time>{t.opened_at.slice(0, 10)}</time>
            <span className={`side ${t.side.toLowerCase()}`}>{t.side}</span>
            <code>{t.strategy}</code>
            <span>
              ${Number(t.entry_px).toLocaleString()}
              {t.exit_px ? ` → $${Number(t.exit_px).toLocaleString()}` : ""}
            </span>
            <strong className={Number(t.realized_pnl ?? 0) >= 0 ? "tone-ok" : "tone-err"}>
              {t.realized_pnl ? `$${Number(t.realized_pnl).toFixed(2)}` : "—"}
            </strong>
            <span className="reason">
              {t.exit_reason ?? "open"} <ChevronRight size={13} />
            </span>
          </button>
        ))}
      </div>

      {selected && <TradeDrawer trade={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}

function TradeDrawer({ trade, onClose }: { trade: TradeDetail; onClose: () => void }) {
  return (
    <div className="drawer-backdrop" role="presentation" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <aside className="drawer" role="dialog" aria-modal="true" aria-label={`Trade ${trade.id} detail`}>
        <button className="icon-button drawer-close" aria-label="Close" onClick={onClose}>
          <X size={18} />
        </button>
        <p className="kicker">RECONSTRUCTED ROUND TRIP</p>
        <h1>#{trade.id} · {trade.side}</h1>
        <div className="drawer-summary">
          <span><small>REALIZED</small><strong className={Number(trade.realized_pnl ?? 0) >= 0 ? "tone-ok" : "tone-err"}>{trade.realized_pnl ? `$${Number(trade.realized_pnl).toFixed(2)}` : "—"}</strong></span>
          <span><small>R-MULTIPLE</small><strong>{trade.r_multiple ?? "—"}</strong></span>
          <span><small>ENVIRONMENT</small><strong>{trade.environment}</strong></span>
        </div>
        <h2>Round-trip facts</h2>
        <dl className="detail-grid">
          <div><dt>Strategy</dt><dd>{trade.strategy}</dd></div>
          <div><dt>Entry / exit</dt><dd>${Number(trade.entry_px).toLocaleString()}{trade.exit_px ? ` / $${Number(trade.exit_px).toLocaleString()}` : ""}</dd></div>
          <div><dt>Quantity</dt><dd>{trade.qty} BTC</dd></div>
          <div><dt>Fees</dt><dd>${trade.fees}</dd></div>
          <div><dt>Exit reason</dt><dd>{trade.exit_reason ?? "open"}</dd></div>
        </dl>
        <h2>Linked orders &amp; fills</h2>
        <div className="linked-orders" data-testid="linked-orders">
          {trade.orders.map((o) => (
            <span key={o.client_order_id}>
              <div>
                <strong>{o.client_order_id}</strong>
                <small>{o.type}{o.reduce_only ? " · reduce-only" : ""}</small>
              </div>
              <span className={`pill ${o.status === "FILLED" ? "ok" : "warn"}`}>{o.status}</span>
            </span>
          ))}
          {trade.orders.length === 0 && <p className="tone-muted">No linked orders recorded.</p>}
        </div>
        {trade.side === "SHORT" && (
          <div className="short-risk-callout">
            <div><strong>No short price stop</strong><p>Size-managed, governed by the sleeve breaker and regime exit.</p></div>
          </div>
        )}
      </aside>
    </div>
  );
}
