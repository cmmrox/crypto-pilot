import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { Link } from "react-router-dom";
import {
  Activity,
  ArrowRight,
  CalendarClock,
  CircleDollarSign,
  Clock3,
  Database,
  Newspaper,
  PauseCircle,
  Play,
  Radio,
  ShieldAlert,
  ShieldCheck,
  Square,
  TrendingDown,
  TrendingUp,
  Wallet,
  Zap,
} from "lucide-react";
import { Area, AreaChart, ResponsiveContainer, Tooltip, YAxis } from "recharts";
import {
  getOverview,
  killSwitch,
  startBot,
  stopBot,
  stopCloseBot,
  type Overview as OverviewData,
} from "../api/client";
import { ConfirmModal, type ModalSpec } from "../components/ConfirmModal";
import { LoadingState, Spinner } from "../components/AsyncState";
import { usePolling } from "../hooks/usePolling";

const POLL_MS = 4000;

function decimalParts(value: string): { negative: boolean; whole: string; fraction: string } {
  const negative = value.trim().startsWith("-");
  const unsigned = value.trim().replace(/^[+-]/, "");
  const [rawWhole = "0", rawFraction = ""] = unsigned.split(".");
  const whole = rawWhole.replace(/^0+(?=\d)/, "") || "0";
  return { negative, whole, fraction: rawFraction };
}

function fixedDecimal(value: string, places = 2): string {
  const { negative, whole, fraction } = decimalParts(value);
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const decimals = fraction.padEnd(places, "0").slice(0, places);
  return `${negative ? "-" : ""}${grouped}${places > 0 ? `.${decimals}` : ""}`;
}

function signedMoney(value: string): string {
  const prefix = value.trim().startsWith("-") ? "−$" : "$";
  return `${prefix}${fixedDecimal(value.replace(/^-/, ""))}`;
}

function isNegative(value: string | null | undefined): boolean {
  return Boolean(value?.trim().startsWith("-"));
}

function dateTime(value: string | null): string {
  if (!value) return "Not yet observed";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZone: "UTC",
    timeZoneName: "short",
  }).format(new Date(value));
}

function relativeTime(value: string | null, now: number): string {
  if (!value) return "never";
  const seconds = Math.max(0, Math.floor((now - new Date(value).getTime()) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  return `${Math.floor(seconds / 3600)}h ago`;
}

function countdown(target: string, now: number): string {
  const remaining = Math.max(0, Math.floor((new Date(target).getTime() - now) / 1000));
  const hours = Math.floor(remaining / 3600);
  const minutes = Math.floor((remaining % 3600) / 60);
  const seconds = remaining % 60;
  return [hours, minutes, seconds].map((part) => String(part).padStart(2, "0")).join(":");
}

export function Overview() {
  const [data, setData] = useState<OverviewData | null>(null);
  const [modal, setModal] = useState<ModalSpec | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [pollError, setPollError] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const refreshInFlight = useRef(false);

  const load = useCallback(async () => {
    if (refreshInFlight.current) return;
    refreshInFlight.current = true;
    try {
      setData(await getOverview());
      setPollError(null);
    } catch (error) {
      setPollError(error instanceof Error ? error.message : "Overview refresh failed");
    } finally {
      refreshInFlight.current = false;
    }
  }, []);

  usePolling(() => void load(), POLL_MS);
  useEffect(() => {
    const clock = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(clock);
  }, []);

  const showToast = (message: string) => {
    setToast(message);
    window.setTimeout(() => setToast(null), 4000);
  };

  const running = data?.bot_status === "running";
  const safeMode = data?.bot_status === "safe_mode";
  const checkedAge = data ? Math.max(0, (now - new Date(data.checked_at).getTime()) / 1000) : null;
  const responseStale = checkedAge === null || checkedAge > (data?.fresh_for_seconds ?? 10);

  const act = async (fn: () => Promise<unknown>, message: string) => {
    await fn();
    showToast(message);
    void load();
  };

  const marketChangeNegative = isNegative(data?.market.price_change_24h_pct);
  const nextDecision = data ? countdown(data.market.next_close_utc, now) : "--:--:--";
  const watchRules = data?.watch.rules ?? [];
  const chartData = useMemo(() => data?.market.sparkline ?? [], [data?.market.sparkline]);

  return (
    <div className="view-stack command-center">
      <div className="page-heading command-heading">
        <div className="command-title-copy">
          <p className="kicker">FR-02 · OWNER COMMAND CENTER</p>
          <h1 data-testid="view-title">Overview</h1>
          <p>Live operations, market context, and closed-candle strategy watch</p>
        </div>
        <div className="heading-actions command-actions">
          {!data ? (
            <button className="button secondary" disabled>
              <Spinner /> Checking status…
            </button>
          ) : running || safeMode ? (
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
              disabled={!data || Boolean(pollError) || responseStale}
              onClick={() =>
                setModal({
                  tone: "warning",
                  kicker: "RECONCILE & START",
                  title: `Start on ${data?.environment ?? "Unavailable"}?`,
                  body: "CryptoPilot connects to Binance, reconciles account truth, then begins the 24/7 loop.",
                  details: [
                    "No action before reconciliation",
                    "Mismatch → safe mode",
                    "Decisions only at 4h close",
                  ],
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
            disabled={!data}
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
            disabled={!data}
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
      {pollError && (
        <div className="banner err" data-testid="overview-refresh-error">
          <Radio size={18} /> Live refresh failed: {pollError}. Last known values remain visible and
          are marked stale.
        </div>
      )}

      <section className="engine-status-rail panel" data-testid="engine-status-rail">
        <div className="engine-state">
          <span
            className={`status-pill ${!data || safeMode ? "warn" : running && data.engine.worker_healthy ? "ok" : "danger"}`}
            data-testid="bot-status"
          >
            <i className="dot" />
            {!data
              ? "Checking status"
              : safeMode
                ? "Safe mode"
                : running
                  ? "Bot running"
                  : "Bot stopped"}
          </span>
          <div>
            <strong>
              {!data
                ? "Confirming background worker"
                : data.engine.worker_healthy
                  ? "Background worker is responsive"
                  : "Background worker is not confirmed"}
            </strong>
            <small data-testid="heartbeat-age">
              Heartbeat {relativeTime(data?.engine.heartbeat_at ?? null, now)}
              {data?.engine.heartbeat_age_seconds != null
                ? ` · ${data.engine.heartbeat_age_seconds.toFixed(1)}s at last poll`
                : ""}
            </small>
          </div>
        </div>
        <RailCheck
          icon={<Activity size={15} />}
          label="Scheduler"
          value={data?.engine.scheduler_alive ? "Alive" : "Stopped"}
          ok={Boolean(data?.engine.scheduler_alive)}
        />
        <RailCheck
          icon={<Database size={15} />}
          label="Database"
          value={data?.engine.database === "ok" ? "Connected" : "Unavailable"}
          ok={data?.engine.database === "ok"}
        />
        <RailCheck
          icon={<Radio size={15} />}
          label="Market feed"
          value={data?.market.reachable && !data.market.stale ? "Live" : "Stale"}
          ok={Boolean(data?.market.reachable && !data.market.stale && !responseStale)}
        />
        <div className="rail-updated">
          <small>Last dashboard check</small>
          <strong>{relativeTime(data?.checked_at ?? null, now)}</strong>
        </div>
      </section>

      {!data ? (
        <div className="panel overview-loading" data-testid="overview-loading">
          <LoadingState
            title="Loading the live command center…"
            detail="Confirming the worker, market feed, account, and strategy state."
          />
        </div>
      ) : (
        <>
          {!data.account_available && (
            <div className="banner warn" data-testid="account-unavailable">
              <Wallet size={18} /> Binance account credentials are unavailable. Public market,
              worker, strategy, and news state remain live; account values show zero.
            </div>
          )}

          <div className="command-grid">
            <section className="panel market-card" data-testid="market-panel">
              <div className="card-head">
                <div>
                  <p className="kicker">MARKET NOW · BINANCE MARK PRICE</p>
                  <h2>
                    {data.market.symbol} · {data.market.interval}
                  </h2>
                </div>
                <span
                  className={`source-badge ${data.market.stale || responseStale ? "warn" : "ok"}`}
                >
                  <i className="dot" /> {data.market.stale || responseStale ? "Stale" : "Live"}
                </span>
              </div>
              <div className="market-price-row">
                <div>
                  <strong className="market-price">
                    {data.market.mark_price
                      ? `$${fixedDecimal(data.market.mark_price, 2)}`
                      : "Unavailable"}
                  </strong>
                  <span className={marketChangeNegative ? "tone-err" : "tone-ok"}>
                    {data.market.price_change_24h_pct
                      ? `${marketChangeNegative ? "" : "+"}${fixedDecimal(data.market.price_change_24h_pct, 2)}% 24h`
                      : "24h change unavailable"}
                  </span>
                </div>
                <small>Observed {relativeTime(data.market.observed_at, now)}</small>
              </div>
              <div className="market-sparkline" aria-label="Recent closed 4h candle trend">
                {chartData.length > 1 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={chartData}>
                      <defs>
                        <linearGradient id="marketFill" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="#2ddb91" stopOpacity={0.3} />
                          <stop offset="100%" stopColor="#2ddb91" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <YAxis hide domain={["dataMin - 10", "dataMax + 10"]} />
                      <Tooltip
                        cursor={{ stroke: "#51606a", strokeDasharray: "3 3" }}
                        content={({ active, payload }) =>
                          active && payload?.[0]?.payload ? (
                            <div className="chart-tooltip">
                              <strong>${fixedDecimal(String(payload[0].payload.close), 2)}</strong>
                              <small>{dateTime(String(payload[0].payload.ts))}</small>
                            </div>
                          ) : null
                        }
                      />
                      <Area
                        type="monotone"
                        dataKey="normalized_bps"
                        stroke="#2ddb91"
                        strokeWidth={2}
                        fill="url(#marketFill)"
                        isAnimationActive={false}
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="inline-empty">Waiting for closed-candle history</div>
                )}
              </div>
            </section>

            <section className="panel decision-card" data-testid="next-decision-panel">
              <div className="card-head">
                <div>
                  <p className="kicker">NEXT DECISION WINDOW</p>
                  <h2>4h candle close</h2>
                </div>
                <CalendarClock size={20} />
              </div>
              <strong className="decision-countdown" data-testid="decision-countdown">
                {nextDecision}
              </strong>
              <p>Until {dateTime(data.market.next_close_utc)}</p>
              <div className="decision-rule">
                <Clock3 size={16} />
                <span>Strategy evaluation occurs only after the candle has fully closed.</span>
              </div>
              <small>Latest evaluated close: {dateTime(data.watch.last_closed_at)}</small>
            </section>

            <section className="panel briefing-card" data-testid="news-briefing-panel">
              <div className="card-head">
                <div>
                  <p className="kicker">LATEST NEWS BRIEFING</p>
                  <h2>{data.briefing.sentiment ?? "No briefing yet"}</h2>
                </div>
                <Newspaper size={20} />
              </div>
              {data.briefing.bullets.length > 0 ? (
                <ul className="briefing-list">
                  {data.briefing.bullets.map((bullet, index) => (
                    <li key={`${bullet.source}-${index}`}>
                      <span>{bullet.text}</span>
                      {bullet.source && <small>{bullet.source}</small>}
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="inline-empty">No generated briefing is available.</div>
              )}
              <div className="news-isolation" data-testid="news-isolation-notice">
                <ShieldCheck size={14} /> {data.briefing.isolation_notice}
              </div>
              <Link to="/news" className="card-link">
                Open news briefing <ArrowRight size={14} />
              </Link>
            </section>

            <section className="panel watch-card" data-testid="strategy-watch-panel">
              <div className="card-head">
                <div>
                  <p className="kicker">WHAT THE STRATEGY IS WATCHING</p>
                  <h2>{data.strategy_display_name} · closed-candle state</h2>
                </div>
                <span className="source-badge neutral">
                  {watchRules.filter((rule) => rule.active).length} active
                </span>
              </div>
              {data.watch.available ? (
                <div className="watch-list">
                  {watchRules.map((rule) => (
                    <article
                      key={rule.key}
                      className={`watch-rule ${rule.tone}`}
                      data-testid={`watch-${rule.key}`}
                    >
                      <span className="watch-marker">
                        <i />
                      </span>
                      <div>
                        <div className="watch-rule-head">
                          <strong>{rule.label}</strong>
                          <span>{rule.status}</span>
                        </div>
                        <p>{rule.condition}</p>
                        <small>
                          Threshold $
                          {rule.threshold_price ? fixedDecimal(rule.threshold_price, 2) : "—"}
                          {rule.distance_pct
                            ? ` · mark distance ${fixedDecimal(rule.distance_pct, 2)}%`
                            : ""}
                        </small>
                      </div>
                    </article>
                  ))}
                </div>
              ) : (
                <div className="inline-empty">
                  Strategy inspection is waiting for its required closed-candle history.
                </div>
              )}
              <p className="watch-disclaimer" data-testid="watch-disclaimer">
                <ShieldAlert size={14} /> {data.watch.disclaimer}
              </p>
            </section>

            <aside className="panel activity-card" data-testid="activity-panel">
              <div className="card-head">
                <div>
                  <p className="kicker">RECENT ACTIVITY</p>
                  <h2>Operational timeline</h2>
                </div>
                <Activity size={20} />
              </div>
              <div className="activity-list">
                {data.activity.length ? (
                  data.activity.map((item, index) => (
                    <article key={`${item.ts}-${item.label}-${index}`}>
                      <span className={`timeline-dot ${item.tone}`} />
                      <div>
                        <strong>{item.label}</strong>
                        <p>{item.detail}</p>
                        <small>{relativeTime(item.ts, now)}</small>
                      </div>
                      <span className={`activity-badge ${item.tone}`}>{item.badge}</span>
                    </article>
                  ))
                ) : (
                  <div className="inline-empty">No activity has been recorded yet.</div>
                )}
              </div>
              <Link to="/events" className="card-link">
                Open event ledger <ArrowRight size={14} />
              </Link>
            </aside>

            <div className="stats-grid command-stats">
              <Stat
                label="Account balance"
                value={signedMoney(data.balance)}
                icon={<Wallet size={18} />}
              />
              <Stat
                label="Total equity"
                value={signedMoney(data.equity)}
                icon={<Activity size={18} />}
                tone={isNegative(data.equity) ? "err" : "ok"}
              />
              <Stat
                label="Unrealized P&L"
                value={signedMoney(data.unrealized_pnl)}
                icon={
                  isNegative(data.unrealized_pnl) ? (
                    <TrendingDown size={18} />
                  ) : (
                    <TrendingUp size={18} />
                  )
                }
                tone={isNegative(data.unrealized_pnl) ? "err" : "ok"}
              />
              <Stat
                label="Month realized"
                value={signedMoney(data.month_realized_pnl)}
                icon={<CircleDollarSign size={18} />}
                tone={isNegative(data.month_realized_pnl) ? "err" : undefined}
              />
            </div>

            <section className="panel position-panel" data-testid="position-panel">
              <p className="kicker">OPEN POSITION · LIVE BINANCE TRUTH</p>
              {data.position ? (
                <>
                  <h2>
                    {data.market.symbol} ·{" "}
                    <span className={data.position.side === "SHORT" ? "tone-err" : "tone-ok"}>
                      {data.position.side}
                    </span>
                  </h2>
                  <div className="position-values">
                    <span>
                      <small>Entry</small>
                      <strong>${fixedDecimal(data.position.entry_price)}</strong>
                    </span>
                    <span>
                      <small>Mark</small>
                      <strong>
                        {data.position.mark_price
                          ? `$${fixedDecimal(data.position.mark_price)}`
                          : "Unavailable"}
                      </strong>
                    </span>
                    <span>
                      <small>Quantity</small>
                      <strong>{data.position.qty} BTC</strong>
                    </span>
                    <span>
                      <small>Effective leverage</small>
                      <strong>{data.position.leverage}×</strong>
                    </span>
                    <span>
                      <small>Unrealized P&L</small>
                      <strong
                        className={
                          isNegative(data.position.unrealized_pnl) ? "tone-err" : "tone-ok"
                        }
                      >
                        {signedMoney(data.position.unrealized_pnl)}
                      </strong>
                    </span>
                  </div>
                  {!data.position.has_price_stop && (
                    <div className="short-risk-callout" data-testid="no-stop-callout">
                      <ShieldAlert size={19} />
                      <div>
                        <strong>No price stop — validated size-managed short</strong>
                        <p>
                          Risk is controlled by volatility-scaled size, the independent monthly
                          sleeve breaker, and a closed-candle regime exit.
                        </p>
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <div className="empty-state">
                  <ShieldCheck size={22} />
                  <p>Flat — no open position.</p>
                </div>
              )}
            </section>

            <section className="panel breaker-panel" data-testid="breaker-panel">
              <p className="kicker">INDEPENDENT GUARDRAILS</p>
              <h2>Monthly circuit breakers</h2>
              {data.breakers.map((breaker) => (
                <div
                  className="breaker-item"
                  key={breaker.book}
                  data-testid={`breaker-${breaker.book.split(" ")[0].toLowerCase()}`}
                >
                  <div>
                    <span>
                      {breaker.book.includes("Long") ? (
                        <TrendingUp size={14} />
                      ) : (
                        <TrendingDown size={14} />
                      )}
                      {breaker.book}
                    </span>
                    <strong
                      className={isNegative(breaker.month_to_date_pnl) ? "tone-err" : "tone-ok"}
                    >
                      {breaker.available
                        ? signedMoney(breaker.month_to_date_pnl)
                        : "Account unavailable"}
                    </strong>
                  </div>
                  <div className="breaker-track">
                    <i
                      style={{ "--breaker-progress": `${breaker.progress_pct}%` } as CSSProperties}
                      className={breaker.tripped ? "tripped" : ""}
                    />
                  </div>
                  <small>
                    {breaker.tripped
                      ? "TRIPPED — halted until the 1st"
                      : `Healthy · halts independently at −${breaker.cap_pct}% MTD`}
                  </small>
                </div>
              ))}
            </section>
          </div>
        </>
      )}

      {modal && <ConfirmModal modal={modal} onClose={() => setModal(null)} />}
      {toast && (
        <div className="toast" role="status" data-testid="toast">
          <ShieldCheck size={16} /> {toast}
        </div>
      )}
    </div>
  );
}

function RailCheck({
  icon,
  label,
  value,
  ok,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  ok: boolean;
}) {
  return (
    <div className="rail-check">
      <span className={ok ? "tone-ok" : "tone-err"}>{icon}</span>
      <span>
        <small>{label}</small>
        <strong>{value}</strong>
      </span>
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
