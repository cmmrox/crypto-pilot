"""Generate BUSINESS_SOLUTION_v2.pdf — CryptoPilot BSD v2.0 (Trend Rider v6)."""
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (BaseDocTemplate, Frame, Image, PageBreak,
                                PageTemplate, Paragraph, Spacer, Table,
                                TableStyle, KeepTogether)

PAGE_W, PAGE_H = A4
NAVY = colors.HexColor("#0c2a45")
BLUE = colors.HexColor("#185fa5")
GRAY = colors.HexColor("#5a6b7a")
LIGHT = colors.HexColor("#eef3f8")
BORD = colors.HexColor("#c9d4de")

s_title = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=30, textColor=NAVY, leading=36)
s_sub   = ParagraphStyle("st", fontName="Helvetica", fontSize=13, textColor=GRAY, leading=18)
s_h1    = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=16, textColor=NAVY,
                         spaceBefore=18, spaceAfter=8, leading=20)
s_h2    = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=12.5, textColor=BLUE,
                         spaceBefore=12, spaceAfter=5, leading=16)
s_body  = ParagraphStyle("b", fontName="Helvetica", fontSize=10, textColor=colors.HexColor("#22303c"),
                         leading=14.5, spaceAfter=6)
s_bull  = ParagraphStyle("bl", parent=s_body, leftIndent=14, bulletIndent=4, spaceAfter=3)
s_cell  = ParagraphStyle("c", parent=s_body, fontSize=9, leading=12, spaceAfter=0)
s_cellb = ParagraphStyle("cb", parent=s_cell, fontName="Helvetica-Bold")
s_note  = ParagraphStyle("n", parent=s_body, fontSize=9, textColor=GRAY, leading=12.5)

story = []
A = story.append


def h1(t): A(Paragraph(t, s_h1))
def h2(t): A(Paragraph(t, s_h2))
def p(t):  A(Paragraph(t, s_body))
def bullet(t): A(Paragraph(t, s_bull, bulletText="•"))
def note(t): A(Paragraph(t, s_note))


def tbl(data, widths, header=True):
    rows = [[Paragraph(c, s_cellb if (header and i == 0) else s_cell) for c in row]
            for i, row in enumerate(data)]
    t = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    st = [("GRID", (0, 0), (-1, -1), 0.5, BORD),
          ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
          ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6)]
    if header:
        st += [("BACKGROUND", (0, 0), (-1, 0), LIGHT)]
    t.setStyle(TableStyle(st))
    A(Spacer(1, 4)); A(t); A(Spacer(1, 8))


# ═══════════════════ cover ═══════════════════
A(Spacer(1, 3.2 * cm))
A(Paragraph("CryptoPilot", s_title))
A(Spacer(1, 0.3 * cm))
A(Paragraph("Automated BTC Trading Platform — Business Solution Document", ParagraphStyle(
    "s2", fontName="Helvetica-Bold", fontSize=16, textColor=BLUE, leading=22)))
A(Spacer(1, 0.5 * cm))
A(Paragraph("Automated execution of the validated <b>Trend Rider v6 long/short strategy</b> on Binance USDT-M Futures "
            "— profitable participation in bull markets AND bear markets — with a web dashboard, SMS alerts, "
            "pluggable strategies and an AI market-news assistant.", s_sub))
A(Spacer(1, 1.0 * cm))
tbl([["Field", "Value"],
     ["Document", "Business Solution Document (BSD)"],
     ["Version", "2.0 — supersedes v1.0 (strategy upgraded v5.2 → v6 long/short)"],
     ["Date", "17 July 2026"],
     ["Prepared for", "Project owner (Binance account holder)"],
     ["Stack", "Python 3.11+ · FastAPI · PostgreSQL 16 · React · Docker"],
     ["Trading venue", "Binance USDT-M Futures — DEMO (testnet) first, then LIVE"],
     ["Strategy", "Trend Rider v6: v5.2 long engine + vol-sized short sleeve (LONGSHORT_REPORT.md)"]],
    [4 * cm, 12.5 * cm])
A(Spacer(1, 0.6 * cm))
p("<b>IMPORTANT — RISK NOTICE:</b> This document describes software that trades real money automatically, "
  "including short selling on futures. Backtested performance (2023–2026, fees included, out-of-sample validated) "
  "does not guarantee future results. Leveraged futures can lose more than the amount risked per trade. The system "
  "enforces layered risk controls (vol-targeted sizing, monthly circuit breakers, leverage caps, kill-switch), but "
  "no automated system removes market risk.")
A(PageBreak())

# ═══════════════════ contents ═══════════════════
h1("Contents")
tbl([["§", "Section"],
     ["1", "Executive summary"], ["2", "Business goals and success criteria"],
     ["3", "Scope"], ["4", "System architecture (with diagram)"],
     ["5", "Functional requirements"], ["6", "Non-functional requirements"],
     ["7", "Strategy plugin framework (loose coupling)"],
     ["8", "Binance integration design (DEMO / LIVE)"],
     ["9", "Database design (PostgreSQL)"],
     ["10", "Notification service — notify.lk SMS"],
     ["11", "AI news assistant"], ["12", "Dashboard specification"],
     ["13", "Security design"], ["14", "Testing and rollout plan"],
     ["15", "Deployment and operations"], ["16", "Project plan and estimates"],
     ["17", "Operating costs"], ["18", "Risks and honest limitations"],
     ["19", "Future enhancements"],
     ["A", "Appendix — Trend Rider v6 strategy (validated results)"]],
    [1.2 * cm, 15.3 * cm])
A(PageBreak())

# ═══════════════════ 1 ═══════════════════
h1("1. Executive summary")
p("CryptoPilot is a self-hosted automated trading platform that executes the owner's validated 4-hour BTCUSDT "
  "strategy — <b>Trend Rider v6</b> — on Binance, unattended, 24/7. Version 2.0 of this document upgrades the "
  "traded strategy from the long-only v5.2 to the long/short v6 composite: the identical long engine plus a "
  "volatility-sized, stop-free <b>short sleeve</b> that earns during bear markets instead of sitting flat. In the "
  "3-year backtest (real Binance data, fees included) v6 returned +204.5% with a −17.2% maximum drawdown and made "
  "<b>+31.7% in the out-of-sample bear year</b> in which buy-and-hold lost 41%.")
p("The owner controls the bot from a secure web dashboard: <b>start / stop at any time</b> (24/7 loop while "
  "running), switch between the Binance <b>DEMO (testnet)</b> and <b>LIVE</b> accounts in Settings, watch open "
  "positions and live profit, and review every historical trade. Portfolio figures (balance, positions, income) "
  "are read from the Binance account API — the exchange, not the bot's memory, is the source of truth. Every "
  "significant event — trade opened, trade closed, bot started, bot stopped, breaker, error — is pushed to the "
  "owner's phone by SMS through <b>notify.lk</b>.")
p("The platform is deliberately built in decoupled halves. The trading core is strategy-agnostic: strategies are "
  "plugins behind a fixed interface (now including short intents), so v6 can be swapped or A/B-replaced without "
  "touching execution, risk, dashboard or notification code. A fully separate <b>AI news agent</b> collects daily "
  "crypto/macro news, summarises it with the Claude API and presents a morning briefing on the dashboard — "
  "informational only, never a trading input.")

h1("2. Business goals and success criteria")
tbl([["#", "Goal", "Success criterion"],
     ["G1", "Trade the validated v6 strategy automatically, both directions", "Bot decisions match the reference backtest engine bar-for-bar on the same data (automated parity test)"],
     ["G2", "Earn in bear markets, not just avoid losing", "Short sleeve activates in deep-bear regime and its live behaviour matches Appendix A expectations"],
     ["G3", "Safe rollout", "≥4 weeks on DEMO with zero unexplained deviations before LIVE is enabled"],
     ["G4", "Owner always in control", "Start/Stop/kill-switch work at any moment; SMS arrives ≤60s after each event"],
     ["G5", "Full auditability", "Every decision, order, fill, SMS and error reconstructable from PostgreSQL"],
     ["G6", "Swappable strategy", "A new strategy class can go live with zero changes outside the strategies package"],
     ["G7", "Informed owner", "Daily AI news briefing on dashboard by the configured local time"]],
    [1.1 * cm, 6.4 * cm, 9 * cm])

h1("3. Scope")
h2("In scope (v2)")
bullet("Automated trading of BTCUSDT USDT-M futures on Binance DEMO (testnet) and LIVE, selectable in Settings.")
bullet("Trend Rider v6 exactly as validated: long engine (regime filter, pullback entries, 2.5×ATR stop, TP1 40% "
       "at 1R, breakeven, 4×ATR trail, regime exit, 4% monthly breaker) <b>plus</b> the short sleeve (deep-bear "
       "regime, 75% × vol-scale sizing, no price stop, cover on regime end, separate 4% monthly sleeve breaker).")
bullet("Web dashboard with authentication: bot control, live position, equity curve, trade history, monthly P&L, "
       "news briefing, settings.")
bullet("SMS notifications via notify.lk; full event log in the database.")
bullet("AI news agent with daily scheduled collection and Claude-generated summaries.")
bullet("Docker-based deployment on a small always-on VPS.")
h2("Out of scope (v2)")
bullet("Automatic withdrawals or any transfer of funds (withdrawal permission is never granted to the API key).")
bullet("Multi-coin portfolios, grid/HFT strategies, sub-4h timeframes (all tested and rejected — see reports).")
bullet("News-driven automated trading decisions (news is informational only).")
bullet("Native mobile app (dashboard is responsive; SMS covers push needs).")
A(PageBreak())

# ═══════════════════ 4 ═══════════════════
h1("4. System architecture")
p("CryptoPilot is a modular monolith: one deployable backend with strictly separated internal services plus a React "
  "single-page dashboard. Modules communicate through defined interfaces and PostgreSQL — never by reaching into "
  "each other's internals — so any module (strategy, notifier, news agent) can be replaced in isolation.")
img = Image("diagram_embed.png", width=16.6 * cm, height=16.6 * cm * 2100 / 2880)
A(Spacer(1, 4)); A(img)
note("Figure 1 — Component architecture (also delivered standalone: CryptoPilot_Solution_Diagram.pdf).")
A(Spacer(1, 6))
tbl([["Component", "Responsibility"],
     ["React dashboard", "UI: login, bot Start/Stop/kill-switch, settings (environment, strategy, risk %), live position, equity & trade history, monthly P&L, news briefing."],
     ["FastAPI backend", "JWT auth, REST API, WebSocket push for live updates, bot lifecycle commands, environment-switch guard (bot must be stopped + confirmation)."],
     ["Bot service", "The 24/7 loop: wakes on every closed 4h candle, feeds the strategy plugin, executes returned intents. State survives restarts (auto-resume)."],
     ["Strategy plugin", "Trend Rider v6 behind the Strategy interface; emits abstract intents only (long AND short). Other strategies registered alongside."],
     ["Risk & sizing engine", "Risk % of equity, short-sleeve vol targeting, leverage cap, both monthly breakers, exchange minimums."],
     ["Execution engine", "Order placement/cancel, fills, lot-size rounding, retries, reconciliation against the Binance account."],
     ["Scheduler", "4h candle-close ticks, news cron, health checks, reconnects."],
     ["Notifier", "Event → SMS via notify.lk + database event row."],
     ["News AI agent", "Isolated collect→summarise→publish pipeline (no access to trading or keys)."],
     ["PostgreSQL", "Single source of truth: settings, credentials (encrypted), strategies, runs, trades, orders, equity, events, news."]],
    [4 * cm, 12.5 * cm])
A(PageBreak())

# ═══════════════════ 5 ═══════════════════
h1("5. Functional requirements")
tbl([["ID", "Requirement", "Priority"],
     ["FR-01", "Settings selects the active environment: DEMO (testnet) or LIVE. Each environment stores its own API key pair. Switching requires the bot stopped and shows a confirmation dialog.", "Must"],
     ["FR-02", "Dashboard Start/Stop button controls the bot. Start = connect, reconcile account state, begin 24/7 loop. Stop = stop evaluating (position left as-is by default); optional 'Stop & close' flattens safely. State survives server restarts.", "Must"],
     ["FR-03", "Bot trades Trend Rider v6 rules exactly as validated (Appendix A), LONG and SHORT, acting only on closed 4h candles.", "Must"],
     ["FR-04", "Long sizing: risk % of equity per trade (default 2% live), leverage capped (default 3x). Short sleeve sizing: weight% × min(1, vol-target / realized vol) of equity, resize only when target drifts >20%. Quantities rounded to Binance lot size; min-notional respected.", "Must"],
     ["FR-05", "Portfolio data (balance, positions, income history) is read from the Binance account API and displayed; the account is the source of truth.", "Must"],
     ["FR-06", "SMS via notify.lk for: trade opened (side, price, size), trade closed (P&L, reason), bot started, bot stopped, breaker triggered (long or sleeve), error/pause. Every SMS also logged.", "Must"],
     ["FR-07", "Trade history: filterable list of all trades with entry/exit, fees, R-multiple, exit reason, strategy, environment; CSV export.", "Must"],
     ["FR-08", "Both monthly circuit breakers enforced engine-side: long book −4% month-to-date → flatten + halt longs till the 1st; short sleeve −4% of equity month-to-date → cover + halt shorts till the 1st (independent).", "Must"],
     ["FR-09", "Kill-switch: one click cancels all orders, flattens all positions, stops the bot, sends SMS.", "Must"],
     ["FR-10", "AI news agent produces a daily briefing shown on the dashboard with source links and FOMC/CPI calendar panel; on-demand refresh.", "Should"],
     ["FR-11", "Strategy selection in Settings from registered plugins with editable parameters (validated defaults pre-filled).", "Should"],
     ["FR-12", "Equity snapshots recorded every 4h close; dashboard renders live + historical equity curve vs buy-and-hold.", "Should"]],
    [1.5 * cm, 12.7 * cm, 2.3 * cm])

h1("6. Non-functional requirements")
tbl([["Area", "Requirement"],
     ["Reliability", "Bot auto-reconnects (exchange REST/WS), resumes after crash/restart from persisted state, and reconciles against the exchange before acting. Missed-candle catch-up on reconnect."],
     ["Latency", "Decisions occur once per 4h close; execution within seconds of close is sufficient. No HFT requirements."],
     ["Auditability", "Every decision, order, fill, SMS and error persisted with UTC timestamps; trades reconcile to Binance income history."],
     ["Maintainability", "Strategy, notifier and news modules replaceable behind interfaces; typed Python (mypy); strategy math covered by parity tests against the validated backtest engine."],
     ["Security", "Keys encrypted at rest, TLS everywhere, no withdrawal permission, JWT + argon2 + optional TOTP."],
     ["Portability", "Docker Compose; runs on a $5–10/month VPS (1 vCPU, 1–2 GB RAM)."]],
    [3 * cm, 13.5 * cm])
A(PageBreak())

# ═══════════════════ 7 ═══════════════════
h1("7. Strategy plugin framework (loose coupling)")
p("The strategy never talks to Binance and never sizes positions. It receives candles and current trade state and "
  "returns abstract <b>intents</b>. The execution engine owns sizing, exchange filters and order mechanics. A new "
  "idea is a new class, registered by name, selectable in Settings — zero changes to execution, risk, dashboard or "
  "notifications. v2.0 extends the intent vocabulary with short-side intents for v6.")
tbl([["Interface element", "Meaning"],
     ["Strategy.name / params", "Registered name + parameters editable in Settings (validated defaults)."],
     ["warmup_bars()", "History needed before first decision (v6: 200 bars for SMA200)."],
     ["on_candle(candles, state) → [Intent]", "Called once per closed 4h candle with full account/trade state."],
     ["EnterLong(stop_distance, tp_levels)", "Open long; engine sizes it from risk % and places stop + TP orders."],
     ["EnterShort(weight, vol_target)", "v6 sleeve: open short; engine computes vol-scaled notional and applies the sleeve breaker. No price stop by design."],
     ["ResizeShort(target_notional)", "Adjust short toward vol target when drift >20% (fee-churn guard in engine)."],
     ["MoveStop(price)", "Ratchet-only (engine refuses to lower a long stop)."],
     ["TakePartial(level_id)", "Informational; TP orders rest on the exchange."],
     ["ExitAll(reason)", "Regime death, breaker, manual, kill-switch."],
     ["Halt(until)", "Stand aside (monthly breakers)."]],
    [6.5 * cm, 10 * cm])
p("Registered strategies at launch: <b>trend_rider_v6</b> (default), <b>trend_rider_v52</b> (long-only fallback). "
  "Both are pinned to the exact parameter sets validated in the backtests.")

h1("8. Binance integration design (DEMO / LIVE)")
bullet("<b>Environments.</b> DEMO = Binance USDT-M testnet (testnet.binancefuture.com); LIVE = fapi.binance.com. "
       "Same code path; base URL and key pair come from the active environment row. Nothing else differs.")
bullet("<b>Market data.</b> 4h klines via REST backfill + user-data/kline WebSocket; candles cached in PostgreSQL. "
       "Decisions only on candle close (kline 'closed' flag).")
bullet("<b>Orders — long engine.</b> Entry MARKET on signal close; STOP_MARKET (reduce-only) protective stop; TP1 "
       "LIMIT (reduce-only) for 40%; trail managed by the engine via stop modification on each close.")
bullet("<b>Orders — short sleeve.</b> Entry/resize MARKET (reduce-only on reductions); NO protective price stop "
       "(validated design — size is the risk control); cover MARKET on regime end, sleeve breaker or kill-switch.")
bullet("<b>Account.</b> One-way position mode, isolated margin, leverage set explicitly (cap default 3x, v6 never "
       "needs more than ~1x for the sleeve + ~3.4x worst case long at 5% risk).")
bullet("<b>Reconciliation.</b> On every start and every 4h close the engine compares expected vs actual position/"
       "orders; any mismatch → safe-mode (no new entries) + SMS alert.")
bullet("<b>Rate limits & errors.</b> Exponential backoff, idempotent client order IDs, margin-error (−2019) handling "
       "pauses the bot with SMS.")
A(PageBreak())

# ═══════════════════ 9 ═══════════════════
h1("9. Database design (PostgreSQL)")
p("PostgreSQL 16. All timestamps timestamptz (UTC). numeric(20,8) for prices/quantities — never floats for money.")
tbl([["Table", "Purpose / key columns"],
     ["users", "Dashboard login: id, email, password_hash (argon2), role, totp_secret, created_at."],
     ["app_settings", "Singleton: active_environment (DEMO|LIVE), active_strategy, risk_pct, sleeve_weight_pct, sleeve_vol_target, leverage_cap, sms_enabled, news_sources[], news_time."],
     ["api_credentials", "Per environment: environment, api_key, api_secret_encrypted (AES-GCM via master key from env), created_at."],
     ["strategies", "Registered plugins: name, class_path, params_json, enabled."],
     ["bot_runs", "One row per start→stop: started_at, stopped_at, environment, strategy, stop_reason (user|error|kill), started_by."],
     ["candles", "Cached klines: symbol, interval, open_time PK, o/h/l/c/v."],
     ["trades", "One row per round-trip: opened_at, closed_at, side (LONG|SHORT), entry_px, exit_px, qty, fees, realized_pnl, r_multiple, exit_reason, strategy, environment, bot_run_id."],
     ["orders", "Every exchange order: binance_order_id, trade_id, type, status, price, stop_price, qty, reduce_only, placed_at, filled_at, raw_json."],
     ["equity_snapshots", "Every 4h close: ts, environment, balance, unrealized_pnl, month_to_date_pnl, sleeve_month_pnl."],
     ["events", "Full audit: ts, level, category (trade|bot|breaker|error|sms|news), message, payload_json, sms_status."],
     ["news_items / briefings", "URL-unique raw items; daily Claude summaries with source links."]],
    [3.4 * cm, 13.1 * cm])

h1("10. Notification service — notify.lk SMS")
p("notify.lk HTTP API (user_id + api_key + sender_id, stored like exchange credentials). Fire-and-log: SMS failure "
  "never blocks trading; failures are retried 3× then logged with a dashboard banner.")
tbl([["Event", "Example SMS"],
     ["Trade opened", "CryptoPilot: LONG opened 0.012 BTC @ 63,120. Stop 61,450, TP1 64,790. (DEMO)"],
     ["Short opened", "CryptoPilot: SHORT sleeve opened 0.008 BTC @ 63,120 (48% of equity, vol-scaled). No price stop; covers on regime end."],
     ["Trade closed", "CryptoPilot: LONG closed +2.1% (+$21.30), reason: trailing stop. Month: +4.2%."],
     ["Short resized", "CryptoPilot: SHORT reduced to 31% of equity (vol spike)."],
     ["Bot started", "CryptoPilot: bot STARTED on LIVE, strategy trend_rider_v6, equity $1,024."],
     ["Bot stopped", "CryptoPilot: bot STOPPED by user. Open position left running with its exchange stops."],
     ["Breaker", "CryptoPilot: monthly loss cap hit (−4%). All closed. Halted until the 1st."],
     ["Error", "CryptoPilot ALERT: order rejected (−2019 margin). Bot paused — check dashboard."]],
    [3.4 * cm, 13.1 * cm])
A(PageBreak())

# ═══════════════════ 11 ═══════════════════
h1("11. AI news assistant")
p("A fully separate module — shares only the database and scheduler; no access to trading code or API keys. "
  "Pipeline (daily at the configured local time, plus on-demand refresh):")
bullet("<b>Collect</b> — configured sources: crypto RSS (CoinDesk, CoinTelegraph, Bitcoin Magazine), macro "
       "headlines, plus the static economic calendar (FOMC decision dates, CPI release dates).")
bullet("<b>Deduplicate & store</b> — URL-unique insert into news_items.")
bullet("<b>Summarise</b> — the day's items go to the Claude API (claude-haiku-4-5 default; claude-sonnet-5 "
       "configurable) with a fixed prompt: 5–8 market-relevant bullets, neutral tone, flag anything affecting BTC "
       "volatility (regulation, ETF flows, Fed).")
bullet("<b>Publish</b> — briefing stored and shown on the dashboard with source links and the upcoming FOMC/CPI "
       "panel.")
p("<b>Design rule:</b> the agent is read-only context for the human. Backtests showed event-based trading filters "
  "lose money (IMPROVEMENT_REPORT.md), so news never feeds the strategy. Its practical value on event days: the "
  "owner knows a violent candle is scheduled, so a stop wick-through is expected behaviour, not a malfunction.")

h1("12. Dashboard specification")
tbl([["Screen", "Contents"],
     ["Login", "Email + password (argon2), JWT session, optional TOTP 2FA."],
     ["Overview", "Environment badge (DEMO/LIVE), bot status + Start/Stop + kill-switch, account balance, open position card (side, entry, size, stop or 'size-managed' for shorts, TP1, unrealized P&L), this-month P&L, both breaker meters, equity curve, today's briefing."],
     ["Trades", "Filterable table (side, environment, strategy, month) with per-trade drawer showing orders/fills; CSV export."],
     ["Monthly", "Calendar-month table: trades, realized P&L, fees, breaker status; manual mark-withdrawn action."],
     ["News", "Daily briefing archive, upcoming FOMC/CPI panel, source links."],
     ["Events", "Audit log with level/category filters."],
     ["Settings", "Environment switch (bot must be stopped), API keys (write-only), strategy + parameters, risk %, sleeve weight/vol target, leverage cap, SMS toggles/templates, news sources/time."]],
    [2.6 * cm, 13.9 * cm])
p("Live updates via WebSocket (position, P&L, bot state) so the overview is real-time without refreshing.")
A(PageBreak())

# ═══════════════════ 13 ═══════════════════
h1("13. Security design")
bullet("Binance API keys created with <b>trade + read only — withdrawals disabled</b>; IP-whitelisted to the VPS.")
bullet("Secrets encrypted at rest (AES-GCM) with a master key provided only via environment variable; keys are "
       "write-only in the UI (never displayed back).")
bullet("TLS everywhere (Caddy/Let's Encrypt); dashboard behind JWT + argon2 + optional TOTP; single-owner role.")
bullet("Kill-switch reachable in two clicks from any dashboard screen.")
bullet("Server hardening: non-root containers, firewall (only 443 + SSH), fail2ban, unattended security updates.")
bullet("Backups: nightly encrypted pg_dump to object storage; restore drill part of acceptance.")

h1("14. Testing and rollout plan")
tbl([["Phase", "What happens", "Exit criteria"],
     ["1. Parity tests", "The bot's strategy module replays the 3-year candle history offline; its decisions are diffed bar-by-bar against the validated research engine (final_composite.py).", "Zero decision mismatches; all unit tests green."],
     ["2. Testnet dry-run", "Full stack on Binance DEMO with small equity; all SMS live; forced-failure drills (network cut, restart mid-trade, kill-switch, breaker).", "≥4 weeks; every trade explained; reconciliation clean; SMS ≤60s."],
     ["3. LIVE pilot", "Switch to LIVE in Settings; minimum sizes (1–2% risk, sleeve weight 50%).", "4+ weeks live matching DEMO behaviour; owner sign-off."],
     ["4. Full operation", "Raise to validated defaults (3–5% risk, sleeve 75%) if desired.", "Ongoing monthly review vs Appendix A expectations."]],
    [2.6 * cm, 8.9 * cm, 5 * cm])

h1("15. Deployment and operations")
bullet("Docker Compose: backend (FastAPI + bot + scheduler), postgres, caddy (TLS), dashboard (static build).")
bullet("VPS: 1 vCPU / 2 GB RAM (e.g. Hetzner/DO $6–8/mo); region near Binance endpoints for stable latency.")
bullet("Monitoring: healthcheck endpoint + dead-man's-switch cron (missed 4h tick → SMS); container auto-restart.")
bullet("Logs: structured JSON to stdout, shipped to the events table for anything user-relevant.")
bullet("Upgrades: blue/green — never upgrade with an open position unless the change is hotfix-critical.")
A(PageBreak())

# ═══════════════════ 16 ═══════════════════
h1("16. Project plan and estimates")
tbl([["#", "Work package", "Est. effort"],
     ["WP1", "Repo/CI, Docker skeleton, DB schema + migrations", "3–4 d"],
     ["WP2", "Binance client (REST+WS, testnet/live), candle cache, reconciliation", "4–5 d"],
     ["WP3", "Strategy framework + Trend Rider v6 plugin + parity tests", "4–5 d"],
     ["WP4", "Risk & execution engine (sizing, vol targeting, breakers, orders)", "5–6 d"],
     ["WP5", "FastAPI + auth + WebSocket + bot lifecycle", "3–4 d"],
     ["WP6", "React dashboard (all screens)", "6–8 d"],
     ["WP7", "Notifier (notify.lk) + templates + event log", "1–2 d"],
     ["WP8", "AI news agent + briefing UI", "2–3 d"],
     ["WP9", "Hardening, backups, failure drills, docs", "3–4 d"],
     ["", "Total (single developer)", "≈ 6–7 weeks"]],
    [1.3 * cm, 11 * cm, 4.2 * cm])

h1("17. Operating costs")
tbl([["Item", "Monthly estimate"],
     ["VPS (1 vCPU / 2 GB)", "$6–10"],
     ["notify.lk SMS (~60–120 msgs/mo)", "LKR 300–700 (≈ $1–2.5)"],
     ["Claude API (daily haiku briefing)", "$1–3"],
     ["Backup object storage", "$1"],
     ["Binance fees", "Included in strategy results (0.04–0.05%/side taker)"],
     ["Total fixed", "≈ $10–17 / month"]],
    [8 * cm, 8.5 * cm])

h1("18. Risks and honest limitations")
tbl([["Risk", "Mitigation / honest statement"],
     ["Strategy stops working", "Trend edges decay. Monthly review vs Appendix A; breakers cap damage; kill-switch always available. No guarantee of future returns."],
     ["Short sleeve has no price stop", "By validated design (stops destroy the short edge). Risk is bounded instead by vol-targeted size (≤75% of equity, shrinks in crashes) + the −4% monthly sleeve breaker + regime exit. Worst backtested month −7.9%."],
     ["Funding rates not modeled", "Shorts usually RECEIVE funding in bears (helps), but this is unmodeled; live funding is recorded per trade and reviewed monthly."],
     ["Exchange/technical outage", "Reconciliation + safe-mode + SMS; exchange-resident stop orders protect the long book even if the VPS dies. The stop-free short is covered by the dead-man's-switch alert to the owner."],
     ["Wick-through / slippage", "Stops are STOP_MARKET; backtest assumed conservative fills and survives 2.5× fee/slippage stress."],
     ["Key compromise", "No withdrawal permission + IP whitelist bounds worst case to bad trades; kill-switch + key rotation runbook."],
     ["Regulatory/venue risk", "Binance availability in the owner's jurisdiction is the owner's responsibility; testnet has no such exposure."],
     ["Owner expectation risk", "23/37 backtested months green; single-digit red months WILL happen (worst −7.9%). 'Profit every month' does not exist honestly — documented three times in the research reports."]],
    [4.2 * cm, 12.3 * cm])

h1("19. Future enhancements")
bullet("A/B parallel strategies on split equity (framework already supports registration).")
bullet("Funding-rate capture reporting; ETH sleeve (structure validated OOS-positive on ETH).")
bullet("Telegram bot as second notification channel; monthly PDF performance report.")
bullet("Withdrawal planner UI implementing the validated 10% monthly-profit rule (manual execution only).")
A(PageBreak())

# ═══════════════════ appendix ═══════════════════
h1("Appendix A — Trend Rider v6 strategy (validated results)")
p("<b>Data & method:</b> real Binance BTCUSDT 4h klines 2023-06 → 2026-07, fees 0.04–0.05%/side included, "
  "conservative fills, in-sample / out-of-sample discipline (OOS = the untouched 2025-07 → 2026-07 bear year). "
  "Full research: LONGSHORT_REPORT.md, BACKTEST_REPORT.md, IMPROVEMENT_REPORT.md.")
h2("Rules")
bullet("<b>Long engine (unchanged v5.2):</b> long only while close &gt; SMA200 and EMA50 &gt; EMA200 (4h). Entries: "
       "fresh regime or EMA20 pullback-resumption. Stop 2.5×ATR(14); TP1 at 1R sells 40% and stop moves to "
       "breakeven; runner trails at highest-high − 4×ATR; exit all if the regime dies; −4% monthly breaker.")
bullet("<b>Short sleeve (v6):</b> short while close &lt; SMA200 − 0.5×ATR and EMA50 &lt; EMA200. Size = 75% × "
       "min(1, 40% / realized vol) of equity (EWMA 48-bar annualized). NO price stop; resize on &gt;20% drift; "
       "cover when the condition fails on a close; −4% monthly sleeve breaker. Long and short regimes are mutually "
       "exclusive — no leverage stacking.")
h2("Validated performance (fees included)")
tbl([["Metric", "Composite v6", "v5.2 long-only", "Buy & hold"],
     ["Total return (3y)", "+204.5%", "+137.3%", "+134.6%"],
     ["CAGR", "+42.7%", "+31.8%", "+31.3%"],
     ["Sharpe", "1.48", "1.45", "0.82"],
     ["Max drawdown", "−17.2%", "−13.2%", "−53.4%"],
     ["Worst month", "−7.9%", "−5.6%", "−20.4%"],
     ["Green months", "23/37", "16/37", "21/37"],
     ["OOS bear year 2025-07→2026-07", "+31.7% (DD −13.8%)", "−2.1%", "−41.4%"],
     ["Log-equity linearity R²", "0.91", "0.82", "0.55"]],
    [5.5 * cm, 4 * cm, 3.6 * cm, 3.4 * cm])
h2("Robustness evidence (why this is not curve-fit)")
bullet("Depth filter 0–1 ATR, vol target 0.3–0.5 (or off), sleeve weight 0.5–1.0: ALL profitable in both windows "
       "(full +174% to +224%, OOS +20% to +44%) — a plateau, not a spike.")
bullet("Survives 0.10%/side costs (2.5× actual). Same structure OOS-positive on ETH (+34%) and BNB (+51%) with "
       "BTC-tuned parameters untouched.")
bullet("Sleeve weight is the smoothness dial: 50% → Sharpe 1.54 / DD −15.9%; 75% (default) → balanced; "
       "100% → +224% / OOS +44%. Halving overall size halves every drawdown and roughly halves returns.")
p("<b>Why the shorts have no stop-loss:</b> every stopped-short variant tested loses — violent bear rallies "
  "whipsaw stops. The validated design controls short risk by position size (vol targeting shrinks the short "
  "automatically in crashes), the monthly sleeve cap, and the regime exit. Do not add a stop in implementation.")

# ═══════════════════ build ═══════════════════
def on_page(canvas, doc):
    canvas.saveState()
    if doc.page > 1:
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(GRAY)
        canvas.drawString(2 * cm, 1.2 * cm, "CryptoPilot — Business Solution Document v2.0")
        canvas.drawRightString(PAGE_W - 2 * cm, 1.2 * cm, f"Confidential · Page {doc.page}")
    canvas.restoreState()


doc = BaseDocTemplate("BUSINESS_SOLUTION_v2.pdf", pagesize=A4,
                      leftMargin=2 * cm, rightMargin=2 * cm,
                      topMargin=1.8 * cm, bottomMargin=1.8 * cm,
                      title="CryptoPilot — Business Solution Document v2.0",
                      author="CryptoPilot project")
frame = Frame(2 * cm, 1.8 * cm, PAGE_W - 4 * cm, PAGE_H - 3.6 * cm, id="f")
doc.addPageTemplates([PageTemplate(id="p", frames=[frame], onPage=on_page)])
doc.build(story)
print("wrote BUSINESS_SOLUTION_v2.pdf")
