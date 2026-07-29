import { useEffect, useRef, useState } from "react";
import { ChevronRight, Database, RefreshCw, Search, Wifi, X, TimerReset } from "lucide-react";
import {
  backfillCandles,
  getEvents,
  getMarketStatus,
  type EventRow,
  type MarketStatus,
} from "../api/client";
import { LoadingState, Spinner } from "../components/AsyncState";
import { Pagination } from "../components/Pagination";
import { useDebouncedValue } from "../hooks/useDebouncedValue";

const PAGE_SIZE = 50;

const CATEGORIES = [
  "",
  "trade",
  "bot",
  "strategy",
  "reconciliation",
  "sms",
  "system",
  "news",
  "security",
  "breaker",
  "error",
];
const LEVELS = ["", "INFO", "WARN", "ERROR"];

export function Events() {
  const [status, setStatus] = useState<MarketStatus | null>(null);
  const [events, setEvents] = useState<EventRow[]>([]);
  const [level, setLevel] = useState("");
  const [category, setCategory] = useState("");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<EventRow | null>(null);
  const [loading, setLoading] = useState(true);
  const [eventsError, setEventsError] = useState("");
  const [statusError, setStatusError] = useState("");
  const [backfillBusy, setBackfillBusy] = useState(false);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const loadSeq = useRef(0);
  const resultsRef = useRef<HTMLDivElement>(null);
  const debouncedSearch = useDebouncedValue(search);

  const loadStatus = async () => {
    setStatusError("");
    try {
      setStatus(await getMarketStatus());
    } catch {
      setStatusError("Could not load market connection status.");
    }
  };

  const loadEvents = async () => {
    setLoading(true);
    setEventsError("");
    const seq = ++loadSeq.current;
    try {
      const result = await getEvents({
        level,
        category,
        search: debouncedSearch,
        page,
        pageSize: PAGE_SIZE,
      });
      if (seq !== loadSeq.current) return;
      if (result.total_pages > 0 && page > result.total_pages) {
        setPage(result.total_pages);
        return;
      }
      setEvents(result.items);
      setTotal(result.total);
      setTotalPages(result.total_pages);
    } catch {
      if (seq === loadSeq.current) {
        setEventsError("Could not load the event ledger. The backend may be unreachable.");
      }
    } finally {
      if (seq === loadSeq.current) setLoading(false);
    }
  };

  const backfill = async () => {
    setBackfillBusy(true);
    setStatusError("");
    try {
      setStatus(await backfillCandles());
      await loadEvents();
    } catch {
      setStatusError("Could not ingest candles. No market data was changed.");
    } finally {
      setBackfillBusy(false);
    }
  };

  useEffect(() => {
    void loadStatus();
  }, []);

  useEffect(() => {
    void loadEvents();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [level, category, debouncedSearch, page]);

  const updateLevel = (next: string) => {
    setPage(1);
    setLevel(next);
  };
  const updateCategory = (next: string) => {
    setPage(1);
    setCategory(next);
  };
  const updateSearch = (next: string) => {
    setPage(1);
    setSearch(next);
  };
  const changePage = (nextPage: number) => {
    setPage(nextPage);
    resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <div className="view-stack">
      <div className="page-heading">
        <div>
          <p className="kicker">FR-02 · SYSTEM & AUDIT</p>
          <h1 data-testid="view-title">Event ledger</h1>
          <p>Every decision, order, fill and error — timestamped in UTC.</p>
        </div>
        <button
          className="button secondary"
          onClick={() => void backfill()}
          data-testid="backfill-btn"
          disabled={backfillBusy}
        >
          {backfillBusy ? (
            <>
              <Spinner /> Ingesting candles…
            </>
          ) : (
            <>
              <RefreshCw size={15} /> Ingest candles now
            </>
          )}
        </button>
      </div>

      <div className="status-grid" data-testid="connection-status">
        <StatusCard
          icon={<Wifi size={16} />}
          label="Binance market data"
          value={status?.exchange_reachable ? "Connected" : "Unreachable"}
          tone={status?.exchange_reachable ? "ok" : "err"}
          sub={status?.clock_drift_ms != null ? `drift ${status.clock_drift_ms} ms` : "—"}
        />
        <StatusCard
          icon={<Database size={16} />}
          label="Candles stored"
          value={status ? String(status.candles_stored) : "—"}
          tone={status && status.gaps === 0 ? "ok" : "warn"}
          sub={status ? `${status.gaps} gap(s)` : "—"}
        />
        <StatusCard
          icon={<TimerReset size={16} />}
          label="Next 4h close"
          value={status ? countdown(status.seconds_to_next_close) : "—"}
          tone="neutral"
          sub={status?.next_close_utc.slice(11, 16) + " UTC"}
        />
        <StatusCard
          icon={<Database size={16} />}
          label="Environment"
          value={status?.environment ?? "—"}
          tone="neutral"
          sub={status?.symbol ?? ""}
        />
      </div>

      <div className="toolbar">
        <label className="search-field">
          <Search size={15} />
          <input
            aria-label="Search events"
            placeholder="Search message or reference"
            value={search}
            onChange={(e) => updateSearch(e.target.value)}
          />
        </label>
        <select
          aria-label="Filter level"
          value={level}
          onChange={(e) => updateLevel(e.target.value)}
        >
          {LEVELS.map((l) => (
            <option key={l} value={l}>
              {l || "All levels"}
            </option>
          ))}
        </select>
        <select
          aria-label="Filter category"
          value={category}
          onChange={(e) => updateCategory(e.target.value)}
        >
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {c || "All categories"}
            </option>
          ))}
        </select>
        <span className="result-count" role="status">
          {loading ? (
            <>
              <Spinner size={13} /> Updating…
            </>
          ) : (
            `${total} events`
          )}
        </span>
      </div>

      {(statusError || eventsError) && (
        <div className="form-error" role="alert">
          {statusError || eventsError}
        </div>
      )}

      <div ref={resultsRef} className="events-panel" data-testid="events-table" aria-busy={loading}>
        <div className="event-head">
          <span>UTC time</span>
          <span>Category</span>
          <span>Level</span>
          <span>Message</span>
          <span>Ref</span>
        </div>
        {loading && events.length === 0 && (
          <LoadingState
            title="Loading event ledger…"
            detail="Fetching the latest audit and system records."
          />
        )}
        {!loading && events.length === 0 && (
          <div className="empty-state">
            <Search size={24} />
            <p>No events match the current filters.</p>
          </div>
        )}
        {events.map((e) => (
          <button
            key={e.id}
            className="event-row"
            onClick={() => setSelected(e)}
            aria-label={`Inspect event ${e.ref ?? e.id}`}
          >
            <time>{e.ts.slice(5, 19).replace("T", " ")}</time>
            <span className="category">{e.category}</span>
            <span className={`level ${e.level.toLowerCase()}`}>{e.level}</span>
            <p>{e.message}</p>
            <span className="event-ref">
              <code>{e.ref ?? "—"}</code>
              <ChevronRight size={13} />
            </span>
          </button>
        ))}
      </div>

      <Pagination
        label="events"
        page={page}
        pageSize={PAGE_SIZE}
        total={total}
        totalPages={totalPages}
        busy={loading}
        onPageChange={changePage}
      />

      {selected && <EventDrawer event={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}

function StatusCard({
  icon,
  label,
  value,
  sub,
  tone,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  sub: string;
  tone: "ok" | "warn" | "err" | "neutral";
}) {
  return (
    <div className="status-card-mini">
      <div className="status-card-top">
        {icon}
        <small>{label}</small>
      </div>
      <strong className={`tone-${tone}`}>{value}</strong>
      <span>{sub}</span>
    </div>
  );
}

function EventDrawer({ event, onClose }: { event: EventRow; onClose: () => void }) {
  return (
    <div
      className="drawer-backdrop"
      role="presentation"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <aside className="drawer" role="dialog" aria-modal="true" aria-label="Event detail">
        <button className="icon-button drawer-close" aria-label="Close" onClick={onClose}>
          <X size={18} />
        </button>
        <p className="kicker">RECONSTRUCTABLE AUDIT RECORD</p>
        <h1>{event.ref ?? `Event ${event.id}`}</h1>
        <div className="drawer-summary">
          <span>
            <small>LEVEL</small>
            <strong className={`level ${event.level.toLowerCase()}`}>{event.level}</strong>
          </span>
          <span>
            <small>CATEGORY</small>
            <strong>{event.category}</strong>
          </span>
          <span>
            <small>SMS</small>
            <strong>{event.sms_status ?? "None"}</strong>
          </span>
        </div>
        <h2>Event</h2>
        <dl className="detail-grid">
          <div>
            <dt>UTC timestamp</dt>
            <dd>{event.ts}</dd>
          </div>
          <div>
            <dt>Message</dt>
            <dd>{event.message}</dd>
          </div>
        </dl>
        <h2>payload_json</h2>
        <pre className="payload-json" data-testid="payload-json">
          {JSON.stringify(event.payload_json, null, 2)}
        </pre>
      </aside>
    </div>
  );
}

function countdown(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return `${h}h ${m}m`;
}
