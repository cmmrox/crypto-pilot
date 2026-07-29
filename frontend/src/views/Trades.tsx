import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
import { LoadingState, Spinner } from "../components/AsyncState";
import { Pagination } from "../components/Pagination";
import { useDebouncedValue } from "../hooks/useDebouncedValue";
import { formatUsd, isNegativeDecimal } from "../utils/decimal";

const PAGE_SIZE = 50;

export function Trades() {
  const [rows, setRows] = useState<TradeRow[]>([]);
  const [filters, setFilters] = useState<TradeFilters>({});
  const [selected, setSelected] = useState<TradeDetail | null>(null);
  const [strategies, setStrategies] = useState<StrategyInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [exporting, setExporting] = useState(false);
  const [detailId, setDetailId] = useState<number | null>(null);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const loadSeq = useRef(0);
  const resultsRef = useRef<HTMLDivElement>(null);
  const debouncedSearch = useDebouncedValue(filters.search ?? "");
  const queryFilters = useMemo<TradeFilters>(
    () => ({
      side: filters.side,
      environment: filters.environment,
      strategy: filters.strategy,
      month: filters.month,
      search: debouncedSearch || undefined,
    }),
    [debouncedSearch, filters.environment, filters.month, filters.side, filters.strategy],
  );

  const load = useCallback(async () => {
    const seq = ++loadSeq.current;
    setLoading(true);
    setError("");
    try {
      const result = await getTrades(queryFilters, page, PAGE_SIZE);
      if (seq !== loadSeq.current) return;
      if (result.total_pages > 0 && page > result.total_pages) {
        setPage(result.total_pages);
        return;
      }
      setRows(result.items);
      setTotal(result.total);
      setTotalPages(result.total_pages);
    } catch {
      if (seq === loadSeq.current) {
        setRows([]);
        setError("Could not load trade history. Check the connection and try again.");
      }
    } finally {
      if (seq === loadSeq.current) setLoading(false);
    }
  }, [page, queryFilters]);

  useEffect(() => {
    void load();
  }, [load]);
  useEffect(() => {
    getStrategies()
      .then(setStrategies)
      .catch(() => setStrategies([]));
  }, []);

  const setF = (k: keyof TradeFilters, v: string) => {
    setPage(1);
    setFilters((filtersBefore) => ({ ...filtersBefore, [k]: v }));
  };
  const reset = () => {
    setPage(1);
    setFilters({});
  };
  const changePage = (nextPage: number) => {
    setPage(nextPage);
    resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const exportCsv = async () => {
    setExporting(true);
    setError("");
    try {
      const text = await getTradesCsv(filters);
      const blob = new Blob([text], { type: "text/csv" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "cryptopilot-trades.csv";
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      setError("Could not export the current trade history.");
    } finally {
      setExporting(false);
    }
  };

  const openDetail = async (id: number) => {
    setDetailId(id);
    setError("");
    try {
      setSelected(await getTradeDetail(id));
    } catch {
      setError(`Could not load trade #${id}.`);
    } finally {
      setDetailId(null);
    }
  };

  return (
    <div className="view-stack">
      <div className="page-heading">
        <div>
          <p className="kicker">FR-07 · RECONCILED HISTORY</p>
          <h1 data-testid="view-title">Trades</h1>
          <p>Every round trip, order and fill — reconciled to Binance.</p>
        </div>
        <button
          className="button secondary"
          data-testid="export-csv"
          onClick={() => void exportCsv()}
          disabled={exporting}
        >
          {exporting ? (
            <>
              <Spinner /> Preparing CSV…
            </>
          ) : (
            <>
              <Download size={15} /> Export CSV
            </>
          )}
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
        <select
          aria-label="Filter by side"
          value={filters.side ?? ""}
          onChange={(e) => setF("side", e.target.value)}
        >
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
        <span className="result-count" role="status">
          {loading ? (
            <>
              <Spinner size={13} /> Updating…
            </>
          ) : (
            `${total} trades`
          )}
        </span>
      </div>

      {error && (
        <div className="form-error" role="alert">
          {error}
        </div>
      )}

      <div ref={resultsRef} className="events-panel" data-testid="trades-table" aria-busy={loading}>
        <div className="trade-head">
          <span>Trade</span>
          <span>Opened</span>
          <span>Side</span>
          <span>Strategy</span>
          <span>Entry / exit</span>
          <span>Realized</span>
          <span>Reason</span>
        </div>
        {loading && rows.length === 0 && (
          <LoadingState
            title="Loading trade history…"
            detail="Reconciling the latest recorded round trips."
          />
        )}
        {!loading && rows.length === 0 && !error && (
          <div className="empty-state">
            <Search size={24} />
            <p>No matching trades.</p>
          </div>
        )}
        {rows.map((t) => (
          <button
            key={t.id}
            className="trade-row"
            onClick={() => void openDetail(t.id)}
            aria-label={`Trade ${t.id} detail`}
            aria-busy={detailId === t.id}
          >
            <span>
              <strong>#{t.id}</strong>
              <em className={`outcome ${t.outcome.toLowerCase()}`}>{t.outcome}</em>
            </span>
            <time>{t.opened_at.slice(0, 10)}</time>
            <span className={`side ${t.side.toLowerCase()}`}>{t.side}</span>
            <code>{t.strategy}</code>
            <span>
              {formatUsd(t.entry_px)}
              {t.exit_px ? ` → ${formatUsd(t.exit_px)}` : ""}
            </span>
            <strong className={isNegativeDecimal(t.realized_pnl) ? "tone-err" : "tone-ok"}>
              {t.realized_pnl ? formatUsd(t.realized_pnl) : "—"}
            </strong>
            <span className="reason">
              {detailId === t.id ? (
                <Spinner size={13} label={`Loading trade ${t.id}`} />
              ) : (
                <>
                  {t.exit_reason ?? "open"} <ChevronRight size={13} />
                </>
              )}
            </span>
          </button>
        ))}
      </div>

      <Pagination
        label="trades"
        page={page}
        pageSize={PAGE_SIZE}
        total={total}
        totalPages={totalPages}
        busy={loading}
        onPageChange={changePage}
      />

      {selected && <TradeDrawer trade={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}

function TradeDrawer({ trade, onClose }: { trade: TradeDetail; onClose: () => void }) {
  return (
    <div
      className="drawer-backdrop"
      role="presentation"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <aside
        className="drawer"
        role="dialog"
        aria-modal="true"
        aria-label={`Trade ${trade.id} detail`}
      >
        <button className="icon-button drawer-close" aria-label="Close" onClick={onClose}>
          <X size={18} />
        </button>
        <p className="kicker">RECONSTRUCTED ROUND TRIP</p>
        <h1>
          #{trade.id} · {trade.side}
        </h1>
        <div className="drawer-summary">
          <span>
            <small>REALIZED</small>
            <strong className={isNegativeDecimal(trade.realized_pnl) ? "tone-err" : "tone-ok"}>
              {trade.realized_pnl ? formatUsd(trade.realized_pnl) : "—"}
            </strong>
          </span>
          <span>
            <small>R-MULTIPLE</small>
            <strong>{trade.r_multiple ?? "—"}</strong>
          </span>
          <span>
            <small>ENVIRONMENT</small>
            <strong>{trade.environment}</strong>
          </span>
        </div>
        <h2>Round-trip facts</h2>
        <dl className="detail-grid">
          <div>
            <dt>Strategy</dt>
            <dd>{trade.strategy}</dd>
          </div>
          <div>
            <dt>Entry / exit</dt>
            <dd>
              {formatUsd(trade.entry_px)}
              {trade.exit_px ? ` / ${formatUsd(trade.exit_px)}` : ""}
            </dd>
          </div>
          <div>
            <dt>Quantity</dt>
            <dd>{trade.qty} BTC</dd>
          </div>
          <div>
            <dt>Fees</dt>
            <dd>{formatUsd(trade.fees)}</dd>
          </div>
          <div>
            <dt>Exit reason</dt>
            <dd>{trade.exit_reason ?? "open"}</dd>
          </div>
        </dl>
        <h2>Linked orders &amp; fills</h2>
        <div className="linked-orders" data-testid="linked-orders">
          {trade.orders.map((o) => (
            <span key={o.client_order_id}>
              <div>
                <strong>{o.client_order_id}</strong>
                <small>
                  {o.type}
                  {o.reduce_only ? " · reduce-only" : ""}
                </small>
              </div>
              <span className={`pill ${o.status === "FILLED" ? "ok" : "warn"}`}>{o.status}</span>
            </span>
          ))}
          {trade.orders.length === 0 && <p className="tone-muted">No linked orders recorded.</p>}
        </div>
        {trade.side === "SHORT" && (
          <div className="short-risk-callout">
            <div>
              <strong>No short price stop</strong>
              <p>Size-managed, governed by the sleeve breaker and regime exit.</p>
            </div>
          </div>
        )}
      </aside>
    </div>
  );
}
