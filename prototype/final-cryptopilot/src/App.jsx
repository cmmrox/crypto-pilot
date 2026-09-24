import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Archive,
  ArrowRight,
  BarChart3,
  Bell,
  Bitcoin,
  BookOpen,
  Bot,
  CalendarDays,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleDollarSign,
  Clock3,
  Cloud,
  Copy,
  Database,
  Download,
  ExternalLink,
  Eye,
  EyeOff,
  FileKey2,
  FileText,
  Gauge,
  HardDrive,
  Info,
  KeyRound,
  LayoutDashboard,
  Library,
  ListTree,
  LockKeyhole,
  LogOut,
  Menu,
  MessageSquareText,
  Newspaper,
  OctagonAlert,
  PauseCircle,
  Play,
  PlugZap,
  RadioTower,
  ReceiptText,
  RefreshCw,
  RotateCcw,
  Search,
  Send,
  Server,
  Settings,
  ShieldAlert,
  ShieldCheck,
  SlidersHorizontal,
  Smartphone,
  Square,
  TestTube2,
  TimerReset,
  TrendingDown,
  TrendingUp,
  UserRound,
  Wallet,
  Waypoints,
  Wifi,
  X,
  Zap,
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const navItems = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "trades", label: "Trades", icon: TrendingUp },
  { id: "monthly", label: "Monthly", icon: CalendarDays },
  { id: "news", label: "News briefing", icon: Newspaper },
  { id: "events", label: "Event ledger", icon: ListTree, count: 3 },
  { id: "settings", label: "Settings", icon: Settings },
];

const equityData = [
  { date: "Jul 23", strategy: 10000, hold: 10000 },
  { date: "Oct 23", strategy: 10300, hold: 10920 },
  { date: "Jan 24", strategy: 10600, hold: 15120 },
  { date: "Apr 24", strategy: 10900, hold: 16600 },
  { date: "Jul 24", strategy: 11200, hold: 15880 },
  { date: "Oct 24", strategy: 11500, hold: 18320 },
  { date: "Jan 25", strategy: 11800, hold: 20480 },
  { date: "Apr 25", strategy: 12100, hold: 21720 },
  { date: "Jul 25", strategy: 12400, hold: 19240 },
  { date: "Oct 25", strategy: 12700, hold: 15120 },
  { date: "Jan 26", strategy: 13000, hold: 13240 },
  { date: "Apr 26", strategy: 13300, hold: 14820 },
  { date: "Jul 26", strategy: 13600, hold: 13460 },
];

const liveShortMarks = [
  64820.34,
  64816.92,
  64824.76,
  64818.44,
  64829.18,
  64821.63,
  64814.07,
];

const tradeRows = [
  {
    id: "TR-2681",
    opened: "17 Jul 04:00",
    closed: "Open",
    side: "SHORT",
    environment: "DEMO",
    strategy: "trend_rider_v6",
    entry: "$65,711.20",
    exit: "—",
    size: "0.142 BTC",
    fees: "$7.24",
    pnl: "+$126.48",
    r: "+0.69R",
    reason: "Active regime",
    month: "2026-07",
    outcome: "OPEN",
  },
  {
    id: "TR-2679",
    opened: "14 Jul 20:00",
    closed: "16 Jul 08:00",
    side: "SHORT",
    environment: "DEMO",
    strategy: "trend_rider_v6",
    entry: "$67,441.08",
    exit: "$65,884.36",
    size: "0.132 BTC",
    fees: "$8.11",
    pnl: "+$205.48",
    r: "+1.11R",
    reason: "Bear regime ended",
    month: "2026-07",
    outcome: "WIN",
  },
  {
    id: "TR-2674",
    opened: "10 Jul 12:00",
    closed: "12 Jul 04:00",
    side: "LONG",
    environment: "DEMO",
    strategy: "trend_rider_v6",
    entry: "$66,105.30",
    exit: "$65,487.12",
    size: "0.291 BTC",
    fees: "$9.42",
    pnl: "−$179.89",
    r: "−1.00R",
    reason: "Initial stop",
    month: "2026-07",
    outcome: "LOSS",
  },
  {
    id: "TR-2670",
    opened: "05 Jul 08:00",
    closed: "08 Jul 16:00",
    side: "LONG",
    environment: "DEMO",
    strategy: "trend_rider_v6",
    entry: "$62,810.44",
    exit: "$64,317.92",
    size: "0.274 BTC",
    fees: "$8.03",
    pnl: "+$413.07",
    r: "+1.82R",
    reason: "4 ATR runner trail",
    month: "2026-07",
    outcome: "WIN",
  },
  {
    id: "TR-2666",
    opened: "01 Jul 00:00",
    closed: "02 Jul 12:00",
    side: "LONG",
    environment: "DEMO",
    strategy: "trend_rider_v6",
    entry: "$61,991.75",
    exit: "$62,237.88",
    size: "0.271 BTC",
    fees: "$5.62",
    pnl: "+$66.84",
    r: "+0.23R",
    reason: "Regime exit",
    month: "2026-07",
    outcome: "WIN",
  },
  {
    id: "TR-2510",
    opened: "18 Jun 04:00",
    closed: "22 Jun 16:00",
    side: "LONG",
    environment: "LIVE",
    strategy: "trend_rider_v52",
    entry: "$58,220.12",
    exit: "$61,811.46",
    size: "0.205 BTC",
    fees: "$11.81",
    pnl: "+$736.23",
    r: "+2.40R",
    reason: "4 ATR runner trail",
    month: "2026-06",
    outcome: "WIN",
  },
];

const eventRows = [
  {
    time: "20:02:14.827",
    date: "17 Jul",
    level: "INFO",
    category: "RECONCILIATION",
    message: "Account state reconciled — position and open orders match Binance",
    ref: "RC-0717",
    sms: "—",
    payload: {
      check_id: "RC-0717",
      environment: "DEMO",
      expected_position: { symbol: "BTCUSDT", side: "SHORT", qty: 0.142 },
      exchange_position: { symbol: "BTCUSDT", side: "SHORT", qty: 0.142 },
      open_orders_expected: 0,
      open_orders_exchange: 0,
      income_last_matched: "TR-2679",
      result: "MATCH",
      latency_ms: 38,
    },
  },
  {
    time: "20:00:07.118",
    date: "17 Jul",
    level: "INFO",
    category: "SMS",
    message: "Status SMS accepted by notify.lk in 1.8 seconds",
    ref: "EV-81283",
    sms: "Delivered",
    payload: {
      provider: "notify.lk",
      sender_id: "CryptoPilot",
      to: "+94 77 ••• ••42",
      body: "CryptoPilot: bot healthy on DEMO, strategy trend_rider_v6, equity $18,545.88.",
      accepted_in_ms: 1804,
      attempt: 1,
      status: "DELIVERED",
    },
  },
  {
    time: "20:00:04.403",
    date: "17 Jul",
    level: "INFO",
    category: "STRATEGY",
    message: "Short sleeve held; 7.2% drift is below the 20% resize threshold",
    ref: "EV-81282",
    sms: "—",
    payload: {
      strategy: "trend_rider_v6",
      intent: "HOLD_SHORT",
      realized_vol_annualized: 0.372,
      vol_target: 0.4,
      target_weight_pct: 53.1,
      current_weight_pct: 49.5,
      drift_pct: 7.2,
      resize_threshold_pct: 20,
      action: "NO_CHANGE",
    },
  },
  {
    time: "20:00:02.221",
    date: "17 Jul",
    level: "INFO",
    category: "BOT",
    message: "Closed 4h candle evaluated — long false, deep-bear true",
    ref: "EV-81281",
    sms: "—",
    payload: {
      candle_close: "2026-07-17T20:00:00Z",
      close: 64821.63,
      sma200: 66890.44,
      ema50: 65120.18,
      ema200: 67340.92,
      atr14: 1180.6,
      long_regime: false,
      deep_bear: true,
      decision: "HOLD_SHORT",
    },
  },
  {
    time: "06:30:11.903",
    date: "17 Jul",
    level: "INFO",
    category: "NEWS",
    message: "Daily briefing published from 7 URL-unique source items",
    ref: "EV-81218",
    sms: "—",
    payload: {
      briefing_id: "BR-2026-07-17",
      model: "claude-haiku-4-5",
      source_items: 7,
      unique_urls: 7,
      sentiment: "Neutral-positive",
      isolation: "no exchange keys · no strategy imports",
      generated_at: "2026-07-17T06:30:11Z",
    },
  },
  {
    time: "04:01:19.628",
    date: "17 Jul",
    level: "WARN",
    category: "TRADE",
    message: "Short resized after volatility target drift reached 23.4%",
    ref: "TR-2681",
    sms: "Delivered",
    payload: {
      trade_id: "TR-2681",
      action: "RESIZE_SHORT",
      reason: "vol_target_drift",
      drift_pct: 23.4,
      previous_qty: 0.116,
      new_qty: 0.142,
      order_type: "MARKET",
      reduce_only: false,
      client_order_id: "CP-TR-2681-03",
    },
  },
  {
    time: "04:00:08.301",
    date: "17 Jul",
    level: "INFO",
    category: "TRADE",
    message: "SHORT opened 0.116 BTC @ $65,711.20 in deep-bear regime",
    ref: "TR-2681",
    sms: "Delivered",
    payload: {
      trade_id: "TR-2681",
      side: "SHORT",
      entry_px: 65711.2,
      qty: 0.116,
      notional_usd: 7622.5,
      weight_pct: 48,
      vol_scaled: true,
      price_stop: null,
      binance_order_id: "BN-9347801",
      client_order_id: "CP-TR-2681-01",
    },
  },
  {
    time: "00:00:03.002",
    date: "17 Jul",
    level: "INFO",
    category: "SYSTEM",
    message: "Dead-man health check passed; next 4h close registered",
    ref: "HC-0717",
    sms: "—",
    payload: {
      check: "dead_man_switch",
      last_tick: "2026-07-17T00:00:00Z",
      next_candle_close: "2026-07-17T04:00:00Z",
      ws_connected: true,
      db_latency_ms: 8,
      result: "PASS",
    },
  },
  {
    time: "23:58:21.104",
    date: "16 Jul",
    level: "ERROR",
    category: "SMS",
    message: "Delivery retry 1 of 3 after provider timeout",
    ref: "EV-81118",
    sms: "Recovered",
    payload: {
      provider: "notify.lk",
      error: "gateway_timeout",
      http_status: 504,
      attempt: 1,
      max_attempts: 3,
      recovered_on_attempt: 2,
      blocked_trading: false,
    },
  },
];

const monthlyRows = [
  ["July 2026", "5", "+$382.16", "−$38.42", "$0.00", "+$343.74", "Healthy", "Healthy"],
  ["June 2026", "8", "+$741.20", "−$61.88", "−$67.93", "+$611.39", "Healthy", "Healthy"],
  ["May 2026", "6", "−$429.81", "−$48.26", "$0.00", "−$478.07", "Tripped 24 May", "Healthy"],
  ["April 2026", "7", "+$918.44", "−$56.04", "−$86.24", "+$776.16", "Healthy", "Healthy"],
  ["March 2026", "9", "+$504.12", "−$73.62", "−$43.05", "+$387.45", "Healthy", "Tripped 19 Mar"],
];

const briefings = [
  {
    date: "17 July",
    title: "Markets hold near a decision point",
    sentiment: "Neutral-positive",
  },
  { date: "16 July", title: "ETF flows offset macro caution", sentiment: "Neutral" },
  { date: "15 July", title: "CPI reaction settles; volatility persists", sentiment: "Cautious" },
  { date: "14 July", title: "Markets prepare for US inflation data", sentiment: "Neutral" },
];

const pageMeta = {
  overview: ["FR-02 · LIVE OPERATIONS", "Overview", "Account truth from Binance · updated just now"],
  trades: ["FR-07 · RECONCILED HISTORY", "Trades", "Every round trip, order and fill matched to Binance income history."],
  monthly: ["FR-08 · WITHDRAWAL DISCIPLINE", "Monthly ledger", "Realized performance, independent breakers and manual withdrawal allowance."],
  news: ["FR-10 · READ-ONLY INTELLIGENCE", "AI market briefing", "Daily crypto and macro context for the owner — never a trading input."],
  events: ["FR-11 · IMMUTABLE AUDIT TRAIL", "System events", "Every decision, order, fill, SMS and error — timestamped in UTC."],
  settings: ["SECURITY & CONFIGURATION", "Settings", "Operational changes are audited; deployed strategy configuration is read-only."],
};

function IconButton({ label, children, className = "", ...props }) {
  return (
    <button className={`icon-button ${className}`} aria-label={label} {...props}>
      {children}
    </button>
  );
}

function StatusPill({ children, tone = "neutral", dot = false }) {
  return (
    <span className={`status-pill ${tone}`}>
      {dot && <i className="status-dot" />}
      {children}
    </span>
  );
}

function Panel({ children, className = "" }) {
  return <section className={`panel ${className}`}>{children}</section>;
}

function PanelHeading({ kicker, title, action, children }) {
  return (
    <div className="panel-heading">
      <div>
        {kicker && <p className="kicker">{kicker}</p>}
        <h2>{title}</h2>
        {children}
      </div>
      {action}
    </div>
  );
}

function StatCard({ label, value, note, tone = "", icon: Icon }) {
  return (
    <Panel className="stat-card">
      <div>
        <span>{label}</span>
        <strong className={tone}>{value}</strong>
        <small>{note}</small>
      </div>
      <span className={`icon-tile ${tone}`}>
        <Icon size={18} />
      </span>
    </Panel>
  );
}

function Login({ onContinue }) {
  const [email, setEmail] = useState("owner@cryptopilot.app");
  const [password, setPassword] = useState("pilot-demo-2026");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");

  const submit = (event) => {
    event.preventDefault();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim()) || password.length < 8) {
      setError("Enter a valid email address and a password of at least eight characters.");
      return;
    }
    setError("");
    onContinue();
  };

  return (
    <main className="auth-shell">
      <section className="auth-story">
        <div className="brand-lockup brand-lockup-large">
          <span className="brand-icon"><Bitcoin size={27} /></span>
          <span>
            <strong>CryptoPilot</strong>
            <small>Trading control room</small>
          </span>
        </div>
        <div className="auth-copy">
          <p className="kicker">OWNER CONSOLE · PROTECTED ACCESS</p>
          <h1>
            Every signal.<br />
            Every safeguard.<br />
            <em>One clear control room.</em>
          </h1>
          <p>
            Operate Trend Rider v6 with closed-candle discipline, exchange reconciliation,
            independent loss breakers and a complete audit trail.
          </p>
        </div>
        <div className="auth-proof-grid">
          <div><ShieldCheck size={20} /><span><strong>Exchange-first truth</strong><small>Binance positions, orders and income are reconciled before action.</small></span></div>
          <div><Clock3 size={20} /><span><strong>4h close only</strong><small>No intrabar trading decisions and no high-frequency behavior.</small></span></div>
          <div><Waypoints size={20} /><span><strong>Validated release</strong><small>Trend Rider v6 · LONG + SHORT · immutable configuration.</small></span></div>
          <div><LockKeyhole size={20} /><span><strong>SMS two-factor</strong><small>A fresh SMS code follows every password sign-in while 2FA is enabled.</small></span></div>
        </div>
      </section>
      <section className="auth-form-wrap">
        <form className="auth-card" onSubmit={submit} noValidate>
          <div className="mobile-auth-brand">
            <span className="brand-icon"><Bitcoin size={22} /></span>
            <strong>CryptoPilot</strong>
          </div>
          <p className="kicker">SINGLE-OWNER WORKSPACE</p>
          <h2>Sign in securely</h2>
          <p>Use your owner credentials. If two-factor is on, an SMS code follows.</p>
          <label>
            Email
            <input
              aria-label="Email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>
          <label>
            Password
            <span className="password-field">
              <input
                aria-label="Password"
                autoComplete="current-password"
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
              <IconButton
                type="button"
                label={showPassword ? "Hide password" : "Show password"}
                onClick={() => setShowPassword((value) => !value)}
              >
                {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
              </IconButton>
            </span>
          </label>
          <div className="auth-meta">
            <label><input type="checkbox" /> Remember email for 14 days</label>
            <span>SMS code still required</span>
          </div>
          {error && <div className="form-error" role="alert"><AlertTriangle size={16} />{error}</div>}
          <button className="button primary full" type="submit">
            Continue <ArrowRight size={16} />
          </button>
          <div className="auth-security-note">
            <ShieldCheck size={16} />
            <span>JWT session · Argon2 password hash · SMS two-factor · TLS-only production access</span>
          </div>
          <small className="prototype-note">Prototype credentials are pre-filled.</small>
        </form>
      </section>
    </main>
  );
}

function Otp({ onVerify, onBack }) {
  const [code, setCode] = useState("");
  const [error, setError] = useState("");

  const submit = (event) => {
    event.preventDefault();
    if (code.replace(/\s/g, "") !== "428916") {
      setError("That SMS code is invalid. Use sample code 428916.");
      return;
    }
    setError("");
    onVerify();
  };

  return (
    <main className="otp-shell">
      <form className="otp-card" onSubmit={submit}>
        <IconButton type="button" label="Back to password" onClick={onBack} className="otp-back">
          <ArrowRight size={17} className="rotate-180" />
        </IconButton>
        <span className="otp-icon"><Smartphone size={24} /></span>
        <p className="kicker">TWO-STEP VERIFICATION</p>
        <h1>Enter your 6-digit code</h1>
        <p>We sent a verification code by SMS to ···· 1234. Enter it below to finish signing in.</p>
        <label className="sr-only" htmlFor="otp">Authentication code</label>
        <input
          id="otp"
          className="otp-input"
          aria-label="Authentication code"
          inputMode="numeric"
          maxLength={6}
          placeholder="000 000"
          value={code}
          onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
          autoFocus
        />
        {error && <div className="form-error" role="alert"><AlertTriangle size={16} />{error}</div>}
        <button className="button primary full" type="submit">Verify & enter</button>
        <div className="otp-required"><ShieldCheck size={15} />The code is single-use and expires after five minutes.</div>
      </form>
    </main>
  );
}

function Sidebar({ activeView, setActiveView, mobileOpen, setMobileOpen, onSignOut }) {
  return (
    <>
      <aside className={`sidebar ${mobileOpen ? "open" : ""}`} aria-label="Primary navigation">
        <div className="sidebar-brand">
          <div className="brand-lockup">
            <span className="brand-icon"><Bitcoin size={22} /></span>
            <span><strong>CryptoPilot</strong><small>Trading control room</small></span>
          </div>
          <IconButton label="Close navigation" className="sidebar-close" onClick={() => setMobileOpen(false)}>
            <X size={18} />
          </IconButton>
        </div>
        <nav>
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.id}
                className={activeView === item.id ? "active" : ""}
                onClick={() => {
                  setActiveView(item.id);
                  setMobileOpen(false);
                  window.scrollTo({ top: 0, behavior: "smooth" });
                }}
              >
                <Icon size={18} />
                <span>{item.label}</span>
                {item.count && <i>{item.count}</i>}
              </button>
            );
          })}
        </nav>
        <div className="sidebar-status">
          <div className="health-card">
            <span className="live-dot" />
            <p><strong>All systems healthy</strong><small>Last reconcile 2m ago</small></p>
          </div>
          <div className="strategy-card-mini">
            <p className="kicker">ACTIVE STRATEGY</p>
            <strong>Trend Rider v6</strong>
            <small>BTCUSDT · 4h · LONG + SHORT</small>
            <span><ShieldCheck size={13} />Validated release 6.0</span>
          </div>
          <button className="sign-out-button" onClick={onSignOut}>
            <LogOut size={16} />Sign out
          </button>
        </div>
      </aside>
      {mobileOpen && <button className="sidebar-scrim" aria-label="Close navigation overlay" onClick={() => setMobileOpen(false)} />}
    </>
  );
}

function Header({
  environment,
  setMobileOpen,
  notificationOpen,
  setNotificationOpen,
  profileOpen,
  setProfileOpen,
  onSignOut,
}) {
  return (
    <header className="topbar">
      <IconButton label="Open navigation" className="mobile-menu" onClick={() => setMobileOpen(true)}>
        <Menu size={19} />
      </IconButton>
      <div className={`environment-badge ${environment === "LIVE" ? "live" : ""}`}>
        <strong>{environment}</strong>
        <span>{environment === "DEMO" ? "Testnet funds" : "Real funds"}</span>
      </div>
      <div className="connection-state"><span className="live-dot" /><strong>Binance connected</strong><small>42 ms</small></div>
      <div className="topbar-actions">
        <div className="popover-wrap">
          <IconButton
            label="Notifications"
            className={notificationOpen ? "active" : ""}
            onClick={() => {
              setNotificationOpen((value) => !value);
              setProfileOpen(false);
            }}
          >
            <Bell size={18} /><i className="notification-count">2</i>
          </IconButton>
          {notificationOpen && (
            <div className="notifications-popover" role="dialog" aria-label="Recent notifications">
              <div className="popover-heading"><div><p className="kicker">ALERT CENTER</p><h2>Recent notifications</h2></div><button>Mark all read</button></div>
              <div className="notification-item unread"><span className="notification-icon warning"><AlertTriangle size={16} /></span><div><strong>SMS delivery recovered</strong><p>Retry 1 of 3 succeeded in 4.2 seconds.</p><small>16 Jul · 23:58 UTC</small></div></div>
              <div className="notification-item unread"><span className="notification-icon success"><CheckCircle2 size={16} /></span><div><strong>Account reconciled</strong><p>Position and open orders match Binance.</p><small>Today · 20:02 UTC</small></div></div>
              <div className="notification-item"><span className="notification-icon"><Newspaper size={16} /></span><div><strong>Morning briefing ready</strong><p>7 source-unique items summarized.</p><small>Today · 06:30 UTC</small></div></div>
            </div>
          )}
        </div>
        <div className="popover-wrap profile-wrap">
          <button
            className="profile-button"
            aria-label="Open owner menu"
            onClick={() => {
              setProfileOpen((value) => !value);
              setNotificationOpen(false);
            }}
          >
            <span>CP</span>
            <div><strong>Project Owner</strong><small>Owner role</small></div>
            <ChevronDown size={16} />
          </button>
          {profileOpen && (
            <div className="profile-popover">
              <button><UserRound size={16} />Owner profile</button>
              <button><KeyRound size={16} />Security</button>
              <button onClick={onSignOut}><LogOut size={16} />Sign out</button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}

function PageHeading({ activeView, botRunning, safeMode, onBotAction, onStopClose, onSafeMode, onKill, onExport }) {
  const [botMenuOpen, setBotMenuOpen] = useState(false);
  const [kicker, title, description] = pageMeta[activeView];
  return (
    <div className="page-heading">
      <div>
        <p className="kicker">{kicker}</p>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      <div className="heading-actions">
        {activeView === "overview" && (
          <>
            <StatusPill tone={safeMode ? "warning" : botRunning ? "success" : "danger"} dot>{safeMode ? "Safe mode" : botRunning ? "Bot running" : "Bot stopped"}</StatusPill>
            <button className="button secondary" onClick={onBotAction}>{botRunning ? <Square size={15} /> : <Play size={15} />}{botRunning ? "Stop bot" : "Start bot"}</button>
            <div className="bot-menu-wrap">
              <IconButton label="More bot controls" onClick={() => setBotMenuOpen((value) => !value)}><ChevronDown size={16} /></IconButton>
              {botMenuOpen && (
                <div className="bot-menu" role="menu">
                  <button onClick={() => { setBotMenuOpen(false); onStopClose(); }}><OctagonAlert size={16} /><span><strong>Stop & close</strong><small>Flatten the position, then stop</small></span></button>
                  <button onClick={() => { setBotMenuOpen(false); onSafeMode(); }}><PauseCircle size={16} /><span><strong>Enter safe mode</strong><small>Block entries; preserve management</small></span></button>
                </div>
              )}
            </div>
            <button className="button danger" onClick={onKill}><Zap size={15} />Kill switch</button>
          </>
        )}
        {activeView === "trades" && <button className="button secondary" onClick={() => onExport("trades")}><Download size={15} />Export CSV</button>}
        {activeView === "monthly" && <button className="button secondary" onClick={() => onExport("monthly")}><Download size={15} />Export ledger</button>}
        {activeView === "news" && <button className="button secondary" onClick={() => onExport("refresh-news")}><RefreshCw size={15} />Refresh briefing</button>}
        {activeView === "events" && <button className="button secondary" onClick={() => onExport("events")}><Download size={15} />Export events</button>}
      </div>
    </div>
  );
}

function Overview({ setActiveView, setSettingsTab, showToast }) {
  const [range, setRange] = useState("ALL");
  const [markIndex, setMarkIndex] = useState(0);
  const chartData = range === "1M" ? equityData.slice(-3) : range === "6M" ? equityData.slice(-7) : equityData;
  const entryPrice = 65711.2;
  const quantity = 0.142;
  const liveMark = liveShortMarks[markIndex];
  const previousMark = liveShortMarks[(markIndex - 1 + liveShortMarks.length) % liveShortMarks.length];
  const unrealizedPnl = (entryPrice - liveMark) * quantity;
  const favorableMove = ((entryPrice - liveMark) / entryPrice) * 100;
  const totalEquity = 18420.63 + unrealizedPnl;
  const priceDirection = liveMark > previousMark ? "up" : "down";
  const money = (value) => value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  useEffect(() => {
    const timer = window.setInterval(() => {
      setMarkIndex((index) => (index + 1) % liveShortMarks.length);
    }, 1800);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <div className="view-stack">
      <Panel className="strategy-hero">
        <div className="strategy-hero-main">
          <span className="strategy-icon"><Waypoints size={22} /></span>
          <div>
            <p className="kicker">STRATEGY CONTROLLING THE BOT</p>
            <h2>Trend Rider v6 <span>Validated & active</span></h2>
            <p><code>trend_rider_v6 · release 6.0</code> · Deployed configuration is read-only</p>
          </div>
        </div>
        <div className="strategy-facts">
          <span><small>Market</small><strong>BTCUSDT</strong></span>
          <span><small>Decision frame</small><strong>Closed 4h candles</strong></span>
          <span><small>Capability</small><strong>LONG + SHORT</strong></span>
          <span><small>Current intent</small><strong className="amber">HOLD SHORT</strong></span>
          <span><small>Last decision</small><strong>20:00:04 UTC</strong></span>
        </div>
        <button
          className="button ghost"
          onClick={() => {
            setSettingsTab("strategy");
            setActiveView("settings");
          }}
        >
          <Library size={15} />Strategy library
        </button>
      </Panel>

      <div className="stats-grid">
        <StatCard label="Account balance" value="$18,420.63" note="Available $8,761.40" icon={Wallet} />
        <StatCard label="Total equity" value={`$${money(totalEquity)}`} note="+$382.16 this month" tone="positive" icon={Activity} />
        <StatCard label="Unrealized P&L" value={`+$${money(unrealizedPnl)}`} note={`${favorableMove.toFixed(2)}% favorable move`} tone="positive" icon={TrendingUp} />
        <StatCard label="Effective exposure" value="53% / 75%" note="Vol-scaled short sleeve" tone="amber" icon={ShieldCheck} />
      </div>

      <div className="overview-grid">
        <Panel className={`position-panel live-position ${priceDirection}`}>
          <PanelHeading
            kicker="OPEN POSITION · LIVE BINANCE TRUTH"
            title="BTCUSDT · Short"
            action={
              <div className="position-statuses">
                <span className="market-stream"><i />Live · 42 ms</span>
                <StatusPill tone="success"><ShieldCheck size={13} />Size-managed</StatusPill>
              </div>
            }
          />
          <div className="position-values">
            <span><small>Entry</small><strong>$65,711.20</strong></span>
            <span className="live-mark">
              <small>Live mark <em>Streaming</em></small>
              <strong key={markIndex} className="positive live-number" aria-label={`Live mark ${money(liveMark)} dollars`}>${money(liveMark)}</strong>
              <b className="positive"><TrendingDown size={12} />{favorableMove.toFixed(2)}% from entry</b>
            </span>
            <span><small>Quantity</small><strong>0.142 BTC</strong></span>
            <span><small>Effective leverage</small><strong>0.53×</strong></span>
          </div>
          <div className="position-highlight">
            <span>
              <small>Unrealized P&L · live</small>
              <strong key={`pnl-${markIndex}`} className="positive live-number">+${money(unrealizedPnl)}</strong>
              <b>Updated from the Binance mark stream</b>
            </span>
            <span>
              <small>Short sleeve month P&L</small>
              <strong className="positive">+0.8%</strong>
              <b>Independent breaker remains healthy</b>
            </span>
          </div>
          <div className="position-state-map" aria-label="Position protection map">
            <div className="state-map-line">
              <span className="state-node danger"><ShieldAlert size={14} /></span>
              <span className="state-node neutral"><CircleDollarSign size={14} /></span>
              <span className="state-node current"><RadioTower size={14} /></span>
              <span className="state-node decision"><Clock3 size={14} /></span>
            </div>
            <div className="state-map-labels">
              <span><strong>−4.0%</strong><small>MONTH BREAKER</small></span>
              <span><strong>53%</strong><small>ACTIVE SIZE</small></span>
              <span><strong className="positive">+${money(unrealizedPnl)}</strong><small>LIVE P&L</small></span>
              <span><strong>4H CLOSE</strong><small>COVER DECISION</small></span>
            </div>
          </div>
          <div className="short-risk-callout">
            <ShieldAlert size={19} />
            <div>
              <strong>No price stop — validated size-managed short</strong>
              <p>Risk is controlled by 53% volatility-scaled size, the independent −4% sleeve breaker, and cover only when the deep-bear regime ends on a closed 4h candle.</p>
            </div>
          </div>
          <div className="position-footer">
            <span><Wifi size={12} />Binance WebSocket connected</span>
            <span>One-way · isolated · resize beyond <strong>20% drift</strong></span>
          </div>
        </Panel>

        <Panel className="chart-panel">
          <PanelHeading
            kicker="PORTFOLIO · 4H SNAPSHOTS"
            title="Equity vs buy-and-hold"
            action={
              <div className="segmented" role="group" aria-label="Chart range">
                {["1M", "6M", "ALL"].map((item) => <button key={item} className={range === item ? "active" : ""} onClick={() => setRange(item)}>{item}</button>)}
              </div>
            }
          />
          <div className="equity-chart" aria-label="Trend Rider v6 equity curve compared with buy and hold">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData} margin={{ top: 10, right: 6, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="strategyFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#2ddb91" stopOpacity={0.28} />
                    <stop offset="100%" stopColor="#2ddb91" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="#273038" strokeDasharray="3 7" vertical={false} />
                <XAxis dataKey="date" tick={{ fill: "#65717a", fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: "#65717a", fontSize: 10 }} tickFormatter={(value) => `$${Math.round(value / 1000)}k`} axisLine={false} tickLine={false} width={42} />
                <Tooltip contentStyle={{ background: "#151c22", border: "1px solid #34404a", borderRadius: 8, fontSize: 11 }} formatter={(value) => [`$${value.toLocaleString()}`, ""]} />
                <Legend iconType="line" wrapperStyle={{ fontSize: 10, color: "#8a969f" }} />
                <Area isAnimationActive={false} name="Trend Rider v6" dataKey="strategy" type="monotone" stroke="#2ddb91" strokeWidth={2.2} fill="url(#strategyFill)" />
                <Area isAnimationActive={false} name="Buy & hold" dataKey="hold" type="monotone" stroke="#65717a" strokeWidth={1.5} strokeDasharray="5 5" fill="transparent" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <div className="chart-proof">
            <strong>Bear-year divergence</strong>
            <p>Illustrative placeholder curve, not a backtest result.</p>
            <small>Prototype mock data · run your own backtest</small>
          </div>
        </Panel>
      </div>

      <div className="dashboard-lower-grid">
        <Panel className="breaker-panel">
          <PanelHeading kicker="INDEPENDENT GUARDRAILS" title="July circuit breakers" action={<StatusPill tone="success">Reset 1 Aug</StatusPill>} />
          <div className="breaker-item">
            <div><span><TrendingUp size={14} />Long book</span><strong className="positive">+1.3%</strong></div>
            <div className="breaker-track"><i style={{ width: "18%" }} /></div>
            <small>Healthy · halts at −4.0% month-to-date</small>
          </div>
          <div className="breaker-item short">
            <div><span><TrendingDown size={14} />Short sleeve</span><strong className="positive">+0.8%</strong></div>
            <div className="breaker-track"><i style={{ width: "12%" }} /></div>
            <small>Healthy · independent cover and halt at −4.0%</small>
          </div>
          <button className="text-button" onClick={() => setActiveView("monthly")}>Review monthly ledger <ChevronRight size={14} /></button>
        </Panel>

        <Panel className="health-panel">
          <PanelHeading kicker="RELIABILITY" title="Execution health" action={<StatusPill tone="success" dot>Healthy</StatusPill>} />
          <div className="health-grid">
            <span><Wifi size={16} /><small>Binance WebSocket</small><strong>Connected · 42 ms</strong></span>
            <span><Database size={16} /><small>PostgreSQL</small><strong>Synced · 8 ms</strong></span>
            <span><TimerReset size={16} /><small>Next closed candle</small><strong>03:53:19</strong></span>
            <span><RadioTower size={16} /><small>Dead-man switch</small><strong>Passed 00:00 UTC</strong></span>
          </div>
          <div className="reconciliation-note"><CheckCircle2 size={16} /><span><strong>Reconciliation #RC-0717 passed.</strong> Position, orders and income match Binance.</span><button onClick={() => setActiveView("events")}>View proof</button></div>
        </Panel>

        <Panel className="monthly-mini">
          <PanelHeading kicker="JULY 2026" title="Monthly performance" action={<button className="text-button" onClick={() => setActiveView("monthly")}>View ledger <ChevronRight size={14} /></button>} />
          <div className="monthly-row"><span>Realized profit</span><strong className="positive">+$382.16</strong></div>
          <div className="monthly-row"><span>Fees & funding</span><strong>−$38.42</strong></div>
          <div className="monthly-row"><span>Withdrawable now</span><strong>$34.37</strong></div>
          <div className="profit-progress"><span /><i>10% of positive realized net profit · manual only</i></div>
        </Panel>

        <Panel className="briefing-mini">
          <PanelHeading kicker="06:30 UTC · 7 SOURCES" title="Morning AI briefing" action={<StatusPill tone="success">Neutral-positive</StatusPill>} />
          <ul>
            <li><span><Check size={12} /></span><div><strong>BTC structure remains constructive</strong><small>Price remains below the deep-bear threshold for the current strategy state.</small></div></li>
            <li><span><Check size={12} /></span><div><strong>ETF flows are modestly positive</strong><small>No abnormal volatility signal in the latest session.</small></div></li>
            <li className="warning"><span><AlertTriangle size={12} /></span><div><strong>US CPI · 23 July, 12:30 UTC</strong><small>Next scheduled high-impact macro event.</small></div></li>
          </ul>
          <button className="button ghost full" onClick={() => setActiveView("news")}>Read full briefing <ChevronRight size={14} /></button>
        </Panel>
      </div>

      <Panel className="scope-banner">
        <Info size={18} />
        <div><strong>Owner boundary</strong><p>CryptoPilot never withdraws funds, never trades from news, never adds coins beyond BTCUSDT, and never acts before a 4h candle closes.</p></div>
        <button className="text-button" onClick={() => showToast("Scope boundary verified", "The final prototype reflects the Business Solution v2 limits.")}>Verify scope</button>
      </Panel>
    </div>
  );
}

function Trades({ selectedTrade, setSelectedTrade }) {
  const [search, setSearch] = useState("");
  const [side, setSide] = useState("");
  const [environment, setEnvironment] = useState("");
  const [strategy, setStrategy] = useState("");
  const [month, setMonth] = useState("");

  const filtered = useMemo(() => tradeRows.filter((trade) => {
    const textMatch = `${trade.id} ${trade.reason}`.toLowerCase().includes(search.toLowerCase());
    return textMatch
      && (!side || trade.side === side)
      && (!environment || trade.environment === environment)
      && (!strategy || trade.strategy === strategy)
      && (!month || trade.month === month);
  }), [search, side, environment, strategy, month]);

  const reset = () => {
    setSearch("");
    setSide("");
    setEnvironment("");
    setStrategy("");
    setMonth("");
  };

  return (
    <div className="view-stack">
      <div className="summary-grid three">
        <StatCard label="Filtered realized P&L" value="+$1,241.73" note="5 closed round trips" tone="positive" icon={CircleDollarSign} />
        <StatCard label="Exchange fees" value="−$50.23" note="Funding included in detail" icon={ReceiptText} />
        <StatCard label="Average R" value="+0.88R" note="Open trade excluded" tone="positive" icon={BarChart3} />
      </div>
      <div className="toolbar">
        <label className="search-field"><Search size={15} /><input aria-label="Search trades" placeholder="Search trade ID or exit reason" value={search} onChange={(event) => setSearch(event.target.value)} /></label>
        <select aria-label="Filter by side" value={side} onChange={(event) => setSide(event.target.value)}><option value="">All sides</option><option>LONG</option><option>SHORT</option></select>
        <select aria-label="Filter by environment" value={environment} onChange={(event) => setEnvironment(event.target.value)}><option value="">All environments</option><option>DEMO</option><option>LIVE</option></select>
        <select aria-label="Filter by strategy" value={strategy} onChange={(event) => setStrategy(event.target.value)}><option value="">All strategies</option><option value="trend_rider_v6">Trend Rider v6</option><option value="trend_rider_v52">Trend Rider v5.2</option></select>
        <input aria-label="Filter by month" type="month" value={month} onChange={(event) => setMonth(event.target.value)} />
        <button className="button ghost" onClick={reset}><RotateCcw size={14} />Reset</button>
        <span className="result-count">{filtered.length} trades</span>
      </div>
      <Panel className="table-panel">
        <div className="table-scroll">
          <table>
            <thead><tr><th>Trade</th><th>Opened / closed</th><th>Side</th><th>Environment</th><th>Strategy</th><th>Entry / exit</th><th>Size</th><th>Fees</th><th>Realized P&L</th><th>R</th><th>Exit reason</th><th /></tr></thead>
            <tbody>
              {filtered.map((trade) => (
                <tr key={trade.id}>
                  <td><strong>{trade.id}</strong><span className={`outcome ${trade.outcome.toLowerCase()}`}>{trade.outcome}</span></td>
                  <td>{trade.opened}<small>{trade.closed}</small></td>
                  <td><span className={`side ${trade.side.toLowerCase()}`}>{trade.side}</span></td>
                  <td>{trade.environment}</td>
                  <td><code>{trade.strategy}</code></td>
                  <td>{trade.entry}<small>{trade.exit}</small></td>
                  <td>{trade.size}</td>
                  <td>{trade.fees}</td>
                  <td className={trade.pnl.startsWith("+") ? "positive" : trade.pnl.includes("−") ? "negative" : ""}><strong>{trade.pnl}</strong></td>
                  <td>{trade.r}</td>
                  <td>{trade.reason}</td>
                  <td><button className="row-button" onClick={() => setSelectedTrade(trade)}>Details <ChevronRight size={13} /></button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!filtered.length && <div className="empty-state"><Search size={26} /><h2>No matching trades</h2><p>Remove a filter or search term to see reconciled trades.</p><button className="button secondary" onClick={reset}>Reset filters</button></div>}
      </Panel>
      {selectedTrade && <TradeDrawer trade={selectedTrade} onClose={() => setSelectedTrade(null)} />}
    </div>
  );
}

function TradeDrawer({ trade, onClose }) {
  return (
    <div className="drawer-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <aside className="drawer" role="dialog" aria-modal="true" aria-label={`${trade.id} trade detail`}>
        <IconButton label="Close trade detail" className="drawer-close" onClick={onClose}><X size={18} /></IconButton>
        <p className="kicker">RECONSTRUCTED ROUND TRIP</p>
        <h1>{trade.id} · {trade.side}</h1>
        <div className="drawer-summary">
          <span><small>REALIZED</small><strong className={trade.pnl.startsWith("+") ? "positive" : "negative"}>{trade.pnl}</strong></span>
          <span><small>R-MULTIPLE</small><strong>{trade.r}</strong></span>
          <span><small>ENVIRONMENT</small><strong>{trade.environment}</strong></span>
        </div>
        <h2>Round-trip facts</h2>
        <dl className="detail-grid">
          <div><dt>Strategy</dt><dd>{trade.strategy}</dd></div>
          <div><dt>Entry / exit</dt><dd>{trade.entry} / {trade.exit}</dd></div>
          <div><dt>Quantity</dt><dd>{trade.size}</dd></div>
          <div><dt>Fees & funding</dt><dd>−{trade.fees}</dd></div>
          <div><dt>Exit reason</dt><dd>{trade.reason}</dd></div>
          <div><dt>Reconciliation</dt><dd className="positive">Matched Binance</dd></div>
        </dl>
        <h2>Linked orders & fills</h2>
        <div className="linked-orders">
          <span><div><strong>#BN-9347801</strong><small>MARKET {trade.side}</small></div><StatusPill tone="success">FILLED</StatusPill></span>
          <span><div><strong>#BN-9349954</strong><small>{trade.side === "SHORT" ? "MARKET COVER" : "REDUCE-ONLY EXIT"}</small></div><StatusPill tone="success">FILLED</StatusPill></span>
          <span><div><strong>CP-{trade.id}-02</strong><small>Idempotent client order ID</small></div><StatusPill>VERIFIED</StatusPill></span>
        </div>
        <h2>Decision timeline</h2>
        <ol className="drawer-timeline">
          <li><i /><div><strong>{trade.opened}</strong><p>Closed candle generated the {trade.side} intent.</p></div></li>
          <li><i /><div><strong>+2.3 sec</strong><p>Risk engine sized the order and passed Binance filters.</p></div></li>
          <li><i /><div><strong>+3.8 sec</strong><p>Entry filled; exchange position reconciled.</p></div></li>
          <li><i /><div><strong>{trade.closed}</strong><p>{trade.reason}; income matched to Binance history.</p></div></li>
        </ol>
        {trade.side === "SHORT" && <div className="short-risk-callout"><ShieldAlert size={18} /><div><strong>No short price stop</strong><p>This round trip was size-managed and governed by the sleeve breaker and regime exit.</p></div></div>}
      </aside>
    </div>
  );
}

function Monthly({ withdrawn, onMarkWithdrawn }) {
  return (
    <div className="view-stack">
      <div className="summary-grid three">
        <StatCard label="July realized P&L" value="+$382.16" note="After $38.42 fees & funding" tone="positive" icon={TrendingUp} />
        <StatCard label="Withdrawable this month" value={withdrawn ? "$0.00" : "$34.37"} note={withdrawn ? "Marked withdrawn 17 Jul" : "10% of positive net profit"} icon={Wallet} />
        <StatCard label="Breaker state" value="Both healthy" note="Independent reset on 1 Aug" tone="positive" icon={ShieldCheck} />
      </div>
      <Panel className="monthly-detail-panel">
        <PanelHeading
          kicker="CALENDAR MONTHS · BINANCE INCOME"
          title="Performance ledger"
          action={<button className="button secondary" onClick={onMarkWithdrawn} disabled={withdrawn}><Wallet size={15} />{withdrawn ? "Withdrawal marked" : "Mark withdrawn"}</button>}
        />
        <div className="table-scroll">
          <table className="monthly-table">
            <thead><tr><th>Month</th><th>Trades</th><th>Realized P&L</th><th>Fees / funding</th><th>Withdrawn</th><th>Net result</th><th>Long breaker</th><th>Short breaker</th></tr></thead>
            <tbody>
              {monthlyRows.map((row, index) => (
                <tr key={row[0]}>
                  {row.map((cell, cellIndex) => {
                    let display = cell;
                    if (index === 0 && cellIndex === 4 && withdrawn) display = "−$34.37";
                    const tone = display.startsWith("+") ? "positive" : display.startsWith("−") && cellIndex !== 3 && cellIndex !== 4 ? "negative" : "";
                    return <td key={`${row[0]}-${cellIndex}`} className={tone}>{cellIndex === 0 ? <strong>{display}</strong> : cellIndex > 5 ? <StatusPill tone={display === "Healthy" ? "success" : "warning"}>{display}</StatusPill> : display}</td>;
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
      <div className="monthly-review-grid">
        <Panel>
          <PanelHeading kicker="SELECTED MONTH" title="July 2026" action={<StatusPill>5 trades</StatusPill>} />
          <div className="waterfall">
            <span><small>Gross winning trades</small><strong className="positive">+$562.05</strong><i><b style={{ width: "82%" }} /></i></span>
            <span><small>Losing trades</small><strong className="negative">−$179.89</strong><i className="red"><b style={{ width: "31%" }} /></i></span>
            <span><small>Exchange fees & funding</small><strong>−$38.42</strong><i className="amber"><b style={{ width: "14%" }} /></i></span>
          </div>
        </Panel>
        <Panel className="withdrawal-rule">
          <ShieldCheck size={22} />
          <div>
            <p className="kicker">WITHDRAWAL RULE APPLIED</p>
            <h2>Manual bookkeeping only</h2>
            <p>max(0, realized net profit) × 10% = $34.37. CryptoPilot never moves funds and the Binance API key never has withdrawal permission.</p>
          </div>
        </Panel>
      </div>
    </div>
  );
}

function News({ showToast }) {
  const [selectedBriefing, setSelectedBriefing] = useState(0);
  return (
    <div className="news-grid">
      <Panel className="briefing-panel">
        <PanelHeading
          kicker="GENERATED 06:30 UTC · CLAUDE HAIKU · 7 SOURCES"
          title={briefings[selectedBriefing].title}
          action={<StatusPill tone="success">{briefings[selectedBriefing].sentiment}</StatusPill>}
        />
        <div className="sentiment-row">
          <span><strong>68</strong><small>Market sentiment</small></span>
          <i><b style={{ width: "68%" }} /></i>
          <p>Neutral-positive</p>
        </div>
        <h3>What matters today</h3>
        <article className="news-insight">
          <span>01</span>
          <div><h4>BTC market structure remains in the validated deep-bear regime</h4><p>Price is below SMA200 − 0.5 ATR while EMA50 remains below EMA200. This context describes the market; only the strategy’s closed-candle rules control the position.</p><a href="https://www.binance.com/en/markets/overview" target="_blank" rel="noreferrer">Binance market data <ExternalLink size={12} /></a></div>
        </article>
        <article className="news-insight">
          <span>02</span>
          <div><h4>ETF flows offer moderate support without a directional signal</h4><p>US spot Bitcoin products recorded a modest net-positive session. Flows remain below June peaks and do not alter automated execution.</p><a href="https://www.coindesk.com/" target="_blank" rel="noreferrer">CoinDesk <ExternalLink size={12} /></a></div>
        </article>
        <article className="news-insight">
          <span>03</span>
          <div><h4>US CPI is the next scheduled high-impact catalyst</h4><p>The 23 July release may increase wick-through and execution slippage. The owner is informed; the bot continues its validated logic unchanged.</p><a href="https://www.bls.gov/schedule/news_release/cpi.htm" target="_blank" rel="noreferrer">US BLS calendar <ExternalLink size={12} /></a></div>
        </article>
        <article className="news-insight">
          <span>04</span>
          <div><h4>Weekend liquidity can widen fills</h4><p>Order-book depth often thins outside US market hours. The execution engine continues to use idempotent orders, exchange filters and reconciliation.</p><a href="https://bitcoinmagazine.com/" target="_blank" rel="noreferrer">Bitcoin Magazine <ExternalLink size={12} /></a></div>
        </article>
        <div className="ai-boundary"><ShieldCheck size={18} /><div><strong>Human context only</strong><p>The news service has no exchange credentials, cannot gate signals and cannot modify Trend Rider v6.</p></div><button onClick={() => showToast("Isolation verified", "The news module shares only PostgreSQL and the scheduler.")}>View boundary</button></div>
      </Panel>
      <aside className="news-sidebar">
        <Panel>
          <PanelHeading kicker="MACRO CALENDAR" title="Upcoming events" />
          <div className="calendar-event high"><time><strong>23</strong><small>JUL</small></time><div><strong>US CPI release</strong><p>12:30 UTC · High impact</p></div></div>
          <div className="calendar-event high"><time><strong>29</strong><small>JUL</small></time><div><strong>FOMC decision</strong><p>18:00 UTC · High impact</p></div></div>
          <div className="calendar-event"><time><strong>01</strong><small>AUG</small></time><div><strong>Breaker reset</strong><p>00:00 UTC · System event</p></div></div>
        </Panel>
        <Panel>
          <PanelHeading kicker="BRIEFING ARCHIVE" title="Recent" />
          <div className="archive-list">
            {briefings.map((briefing, index) => <button key={briefing.date} className={selectedBriefing === index ? "active" : ""} onClick={() => setSelectedBriefing(index)}><span><strong>{briefing.date}</strong><small>{briefing.title}</small></span><ChevronRight size={14} /></button>)}
          </div>
        </Panel>
        <Panel className="sources-panel">
          <PanelHeading kicker="COLLECTION" title="Configured sources" />
          <div className="source-tags"><span>CoinDesk RSS</span><span>Cointelegraph RSS</span><span>Bitcoin Magazine</span><span>Macro headlines</span><span>FOMC / CPI calendar</span></div>
          <p>URL-unique items · neutral 5–8 bullet prompt · daily scheduled publication</p>
        </Panel>
      </aside>
    </div>
  );
}

function Events() {
  const [search, setSearch] = useState("");
  const [level, setLevel] = useState("");
  const [category, setCategory] = useState("");
  const [selectedEvent, setSelectedEvent] = useState(null);
  const filtered = eventRows.filter((event) => {
    const text = `${event.message} ${event.ref}`.toLowerCase();
    return text.includes(search.toLowerCase()) && (!level || event.level === level) && (!category || event.category === category);
  });
  return (
    <div className="view-stack">
      <div className="event-health-grid">
        <Panel><span className="live-dot" /><div><strong>Trading loop</strong><small>Healthy · last tick 18s ago</small></div></Panel>
        <Panel><Wifi size={16} /><div><strong>Binance WebSocket</strong><small>Connected · 42 ms</small></div></Panel>
        <Panel><ShieldCheck size={16} /><div><strong>Reconciliation</strong><small>Match · 20:02 UTC</small></div></Panel>
        <Panel><MessageSquareText size={16} /><div><strong>SMS gateway</strong><small>1 recovered retry today</small></div></Panel>
      </div>
      <div className="toolbar">
        <label className="search-field"><Search size={15} /><input aria-label="Search events" placeholder="Search event message or reference" value={search} onChange={(event) => setSearch(event.target.value)} /></label>
        <select aria-label="Filter event level" value={level} onChange={(event) => setLevel(event.target.value)}><option value="">All levels</option><option>INFO</option><option>WARN</option><option>ERROR</option></select>
        <select aria-label="Filter event category" value={category} onChange={(event) => setCategory(event.target.value)}><option value="">All categories</option>{["TRADE", "BOT", "STRATEGY", "RECONCILIATION", "SMS", "SYSTEM", "NEWS"].map((item) => <option key={item}>{item}</option>)}</select>
        <span className="result-count">Showing {filtered.length}</span>
      </div>
      <Panel className="events-panel">
        <div className="event-table-head"><span>UTC time</span><span>Category</span><span>Level</span><span>Event message</span><span>SMS</span><span>Reference</span></div>
        {filtered.map((event) => (
          <button className="event-row" type="button" key={`${event.date}-${event.time}`} onClick={() => setSelectedEvent(event)} aria-label={`Inspect payload for ${event.ref}`}>
            <time><strong>{event.date}</strong><small>{event.time}</small></time>
            <span className="category">{event.category}</span>
            <span className={`level ${event.level.toLowerCase()}`}>{event.level}</span>
            <p>{event.message}</p>
            <span className={event.sms === "Delivered" ? "positive" : event.sms === "Recovered" ? "amber" : ""}>{event.sms}</span>
            <span className="event-ref"><code>{event.ref}</code><ChevronRight size={13} /></span>
          </button>
        ))}
        {!filtered.length && <div className="empty-state"><Search size={26} /><h2>No matching events</h2><p>Adjust the search term, level or category to see the audit trail.</p></div>}
      </Panel>
      {selectedEvent && <EventDrawer event={selectedEvent} onClose={() => setSelectedEvent(null)} />}
    </div>
  );
}

function EventDrawer({ event, onClose }) {
  return (
    <div className="drawer-backdrop" role="presentation" onMouseDown={(mouseEvent) => mouseEvent.target === mouseEvent.currentTarget && onClose()}>
      <aside className="drawer" role="dialog" aria-modal="true" aria-label={`${event.ref} event payload`}>
        <IconButton label="Close event detail" className="drawer-close" onClick={onClose}><X size={18} /></IconButton>
        <p className="kicker">RECONSTRUCTABLE AUDIT RECORD</p>
        <h1>{event.ref}</h1>
        <div className="drawer-summary">
          <span><small>LEVEL</small><strong className={event.level === "ERROR" ? "negative" : event.level === "WARN" ? "amber" : "positive"}>{event.level}</strong></span>
          <span><small>CATEGORY</small><strong>{event.category}</strong></span>
          <span><small>SMS</small><strong className={event.sms === "Delivered" ? "positive" : event.sms === "Recovered" ? "amber" : ""}>{event.sms === "—" ? "None" : event.sms}</strong></span>
        </div>
        <h2>Event</h2>
        <dl className="detail-grid">
          <div><dt>UTC timestamp</dt><dd>{event.date} · {event.time}</dd></div>
          <div><dt>Reference</dt><dd>{event.ref}</dd></div>
          <div><dt>Message</dt><dd>{event.message}</dd></div>
          <div><dt>Persistence</dt><dd className="positive">Written to events table</dd></div>
        </dl>
        <h2>payload_json</h2>
        <pre className="payload-json">{JSON.stringify(event.payload, null, 2)}</pre>
        <div className="reconciliation-note"><ShieldCheck size={16} /><span>Immutable UTC record — every decision, order, fill, SMS and error is reconstructable from PostgreSQL.</span></div>
      </aside>
    </div>
  );
}

function SettingsView({
  environment,
  setEnvironment,
  botRunning,
  settingsTab,
  setSettingsTab,
  showToast,
  openModal,
}) {
  const tabs = [
    ["environment", "Environment", Server],
    ["strategy", "Strategy library", Library],
    ["credentials", "API credentials", FileKey2],
    ["sms", "SMS alerts", MessageSquareText],
    ["news-config", "News agent", Newspaper],
    ["security", "Security", ShieldCheck],
    ["operations", "Operations", Activity],
  ];

  const requestEnvironment = (target) => {
    if (target === environment) return;
    if (botRunning) {
      openModal({
        tone: "warning",
        icon: ShieldAlert,
        kicker: "ENVIRONMENT SWITCH BLOCKED",
        title: "Stop the bot before switching accounts",
        body: "The running execution loop is bound to the current Binance account. Stop the bot, then return here to confirm the environment change.",
        confirmLabel: "Understood",
      });
      return;
    }
    openModal({
      tone: target === "LIVE" ? "danger" : "warning",
      icon: target === "LIVE" ? AlertTriangle : Server,
      kicker: "GUARDED ENVIRONMENT CHANGE",
      title: `Switch from ${environment} to ${target}?`,
      body: target === "LIVE"
        ? "LIVE uses real funds. CryptoPilot will reconcile the LIVE Binance account before the next start. Type LIVE to confirm."
        : "DEMO uses Binance USDT-M testnet funds and a separate write-only credential pair.",
      confirmWord: target === "LIVE" ? "LIVE" : "",
      confirmLabel: `Switch to ${target}`,
      onConfirm: () => {
        setEnvironment(target);
        showToast(`Environment changed to ${target}`, "The next bot start will reconcile this account before acting.");
      },
    });
  };

  return (
    <div className="settings-layout">
      <nav className="settings-nav" aria-label="Settings sections">
        {tabs.map(([id, label, Icon]) => <button key={id} className={settingsTab === id ? "active" : ""} onClick={() => setSettingsTab(id)}><Icon size={15} />{label}</button>)}
      </nav>
      <div className="settings-content">
        {settingsTab === "environment" && (
          <Panel className="settings-card">
            <SettingsHeading icon={Server} kicker="TRADING VENUE" title="Environment & account" description="DEMO and LIVE use the same code path with completely separate write-only credentials." status={`${environment} active`} />
            <div className="environment-options">
              <button className={environment === "DEMO" ? "active" : ""} onClick={() => requestEnvironment("DEMO")}><span className="env-letter">D</span><span><strong>DEMO / Testnet</strong><small>Fake funds · safe testing</small></span>{environment === "DEMO" && <StatusPill tone="success">Active</StatusPill>}</button>
              <button className={`live ${environment === "LIVE" ? "active" : ""}`} onClick={() => requestEnvironment("LIVE")}><span className="env-letter">L</span><span><strong>LIVE trading</strong><small>Real funds · production</small></span>{environment === "LIVE" && <StatusPill tone="danger">Active</StatusPill>}</button>
            </div>
            <div className="guard-callout"><ShieldAlert size={18} /><div><strong>Switching is blocked while the bot is running</strong><p>Every start connects, reconciles positions/orders and catches up any missed closed candle before new action.</p></div></div>
            <div className="acceptance-grid">
              <span><small>DEMO acceptance</small><strong>Day 19 of 28</strong><i><b style={{ width: "68%" }} /></i></span>
              <span><small>Unexplained deviations</small><strong className="positive">0</strong></span>
              <span><small>SMS delivery ≤60s</small><strong className="positive">100%</strong></span>
              <span><small>LIVE gate</small><strong>Locked until 4 weeks</strong></span>
            </div>
          </Panel>
        )}

        {settingsTab === "strategy" && (
          <>
            <Panel className="settings-card">
              <SettingsHeading icon={Waypoints} kicker="REGISTERED PLUGINS" title="Strategy library" description="Only one strategy controls BTCUSDT. Selection is guarded and available only while stopped." status="2 validated releases" />
              <div className="strategy-library">
                <article>
                  <div><span className="strategy-icon"><Waypoints size={20} /></span><span><p className="kicker">ACTIVE STRATEGY</p><h3>Trend Rider v6</h3><code>trend_rider_v6 · v6.0</code></span><StatusPill tone="success">Active</StatusPill></div>
                  <dl><span><dt>Direction</dt><dd>LONG + SHORT</dd></span><span><dt>Validation</dt><dd>Parity verified</dd></span><span><dt>Updated</dt><dd>17 Jul 2026</dd></span></dl>
                  <button className="button secondary full" disabled>Currently controlling bot</button>
                </article>
                <article className="muted">
                  <div><span className="strategy-icon"><TrendingUp size={20} /></span><span><p className="kicker">AVAILABLE FALLBACK</p><h3>Trend Rider v5.2</h3><code>trend_rider_v52 · v5.2</code></span><StatusPill>Inactive</StatusPill></div>
                  <dl><span><dt>Direction</dt><dd>LONG ONLY</dd></span><span><dt>Validation</dt><dd>Parity verified</dd></span><span><dt>Updated</dt><dd>08 Jun 2026</dd></span></dl>
                  <button
                    className="button secondary full"
                    onClick={() => {
                      if (botRunning) {
                        openModal({ tone: "warning", icon: ShieldAlert, kicker: "STRATEGY SWITCH BLOCKED", title: "Stop the bot before selecting a release", body: "A running plugin cannot be replaced. Stop the bot, return to Strategy library and confirm the validated fallback.", confirmLabel: "Understood" });
                      } else {
                        openModal({ tone: "warning", icon: Library, kicker: "VALIDATED RELEASE CHANGE", title: "Select Trend Rider v5.2?", body: "This fallback is long-only. The switch is audit-logged and applies at the next reconciled start.", confirmLabel: "Select fallback", onConfirm: () => showToast("Fallback selected", "Trend Rider v5.2 will control the next reconciled start.") });
                      }
                    }}
                  >
                    Select while stopped
                  </button>
                </article>
              </div>
            </Panel>
            <Panel className="settings-card read-only-manifest">
              <SettingsHeading icon={LockKeyhole} kicker="DEPLOYED RELEASE" title="Validated configuration — read only" description="Changing a parameter requires a versioned release, parity testing and deployment outside this operator dashboard." status="Operator editing disabled" />
              <div className="manifest-grid">
                <span><small>Decision cadence</small><strong>Closed BTCUSDT 4h candles only</strong></span>
                <span><small>Long regime</small><strong>Close &gt; SMA200 · EMA50 &gt; EMA200</strong></span>
                <span><small>Long execution</small><strong>2% risk · 3× cap · 2.5 ATR stop · TP1 40% @ 1R · 4 ATR trail</strong></span>
                <span><small>Short regime</small><strong>Close &lt; SMA200 − 0.5 ATR · EMA50 &lt; EMA200</strong></span>
                <span><small>Short sizing</small><strong>75% × min(1, 40% / realized vol) · resize beyond 20% drift</strong></span>
                <span><small>Short protection</small><strong>No price stop · size-managed · regime exit · independent breaker</strong></span>
                <span><small>Monthly breakers</small><strong>Long −4% · Short −4% · independent reset on the 1st</strong></span>
                <span><small>Execution filters</small><strong>Binance lot size · min notional · isolated margin · one-way mode</strong></span>
                <span><small>Mutual exclusion</small><strong>Long and short regimes never stack</strong></span>
              </div>
              <div className="release-proof"><CheckCircle2 size={17} /><span><strong>Parity status: zero mismatches.</strong> Replay checked bar-for-bar against `final_composite.py`.</span></div>
            </Panel>
          </>
        )}

        {settingsTab === "credentials" && (
          <>
            <Panel className="settings-card">
              <SettingsHeading icon={FileKey2} kicker="WRITE-ONLY SECRETS" title="Binance API credentials" description="Keys are never returned by the API. Enter a value only to add or replace it." status="AES-GCM encrypted" />
              <CredentialBlock environment="DEMO" configured onTest={() => showToast("DEMO connection passed", "Read access, Futures permission and IP allowlist verified.")} />
              <CredentialBlock environment="LIVE" onTest={() => showToast("LIVE connection unavailable", "Add a LIVE key pair before testing read access.")} />
            </Panel>
            <Panel className="settings-card">
              <SettingsHeading icon={ShieldCheck} kicker="KEY PERMISSIONS" title="Required account controls" description="The production backend rejects unsafe exchange credentials." />
              <div className="security-check-grid"><span><CheckCircle2 size={15} />Futures trading enabled</span><span><CheckCircle2 size={15} />Read access enabled</span><span><CheckCircle2 size={15} />Withdrawals disabled</span><span><CheckCircle2 size={15} />VPS IP allowlisted</span><span><CheckCircle2 size={15} />Isolated margin</span><span><CheckCircle2 size={15} />One-way position mode</span></div>
            </Panel>
          </>
        )}

        {settingsTab === "sms" && <SmsSettings showToast={showToast} />}
        {settingsTab === "news-config" && <NewsSettings showToast={showToast} />}
        {settingsTab === "security" && <SecuritySettings showToast={showToast} openModal={openModal} />}
        {settingsTab === "operations" && <OperationsSettings showToast={showToast} />}
      </div>
    </div>
  );
}

function SettingsHeading({ icon: Icon, kicker, title, description, status }) {
  return (
    <div className="settings-heading">
      <span className="settings-icon"><Icon size={19} /></span>
      <div><p className="kicker">{kicker}</p><h2>{title}</h2><p>{description}</p></div>
      {status && <StatusPill tone="success">{status}</StatusPill>}
    </div>
  );
}

function CredentialBlock({ environment, configured = false, onTest }) {
  return (
    <div className="credential-block">
      <div className="credential-heading"><div><strong>{environment} credentials</strong><small>{environment === "DEMO" ? "Binance USDT-M testnet" : "Binance USDT-M production"}</small></div><StatusPill tone={configured ? "success" : "warning"}>{configured ? "Configured" : "Not configured"}</StatusPill></div>
      <div className="form-grid two">
        <label>API key<input type="password" placeholder={configured ? "Stored securely — enter to replace" : "Enter new API key"} /></label>
        <label>API secret<input type="password" placeholder={configured ? "Stored securely — enter to replace" : "Enter new API secret"} /></label>
      </div>
      <div className="credential-footer"><button className="button secondary" onClick={onTest}><PlugZap size={14} />Test read-only connection</button><span><KeyRound size={14} />{configured ? "Existing key ends ···· 7X2P" : "No secret is stored yet"}</span></div>
    </div>
  );
}

const smsTemplateDefaults = {
  "Trade opened": "CryptoPilot: {{side}} opened {{qty}} BTC @ {{price}}. Stop {{stop}}, TP1 {{tp1}}. ({{environment}})",
  "Short opened": "CryptoPilot: SHORT sleeve opened {{qty}} BTC @ {{price}} ({{weight}} of equity, vol-scaled). No price stop; covers on regime end.",
  "Trade closed": "CryptoPilot: {{side}} closed {{pnl_pct}} ({{pnl}}), reason: {{reason}}. Month: {{month_pnl}}.",
  "Short resized": "CryptoPilot: SHORT resized to {{weight}} of equity ({{reason}}).",
  "Bot started": "CryptoPilot: bot STARTED on {{environment}}, strategy {{strategy}}, equity {{equity}}.",
  "Bot stopped": "CryptoPilot: bot STOPPED by {{actor}}. Open position left running with its exchange stops.",
  "Breaker triggered": "CryptoPilot: monthly loss cap hit (−4%). All closed. Halted until the 1st.",
  "Error / pause": "CryptoPilot ALERT: {{error}}. Bot paused — check dashboard.",
};

function SmsSettings({ showToast }) {
  const [enabled, setEnabled] = useState(true);
  const [templates, setTemplates] = useState(smsTemplateDefaults);
  const [activeTemplate, setActiveTemplate] = useState("Trade opened");
  const template = templates[activeTemplate];
  const setTemplate = (updater) =>
    setTemplates((all) => ({ ...all, [activeTemplate]: typeof updater === "function" ? updater(all[activeTemplate]) : updater }));
  return (
    <Panel className="settings-card">
      <SettingsHeading icon={MessageSquareText} kicker="NOTIFY.LK" title="SMS alerts" description="Fire-and-log delivery; failures retry three times and never block trading." status={enabled ? "Enabled" : "Disabled"} />
      <div className="form-grid two">
        <label>User ID<input type="password" placeholder="Stored securely — enter to replace" /></label>
        <label>API key<input type="password" placeholder="Stored securely — enter to replace" /></label>
        <label>Owner phone<input value="+94 77 ••• ••42" readOnly /></label>
        <label>Sender ID<input value="CryptoPilot" readOnly /></label>
      </div>
      <div className="setting-row"><span><strong>SMS delivery</strong><small>Disable only during maintenance</small></span><button className={`toggle ${enabled ? "on" : ""}`} role="switch" aria-checked={enabled} onClick={() => setEnabled((value) => !value)}><i /></button></div>
      <h3 className="settings-subheading">Notify me when</h3>
      <div className="notification-toggle-grid">
        {["Trade opened or resized", "Trade closed", "Bot started or stopped", "Long breaker triggered", "Short breaker triggered", "Error or reconciliation mismatch"].map((item) => <label key={item}><input type="checkbox" defaultChecked /><span><strong>{item}</strong><small>SMS plus immutable event row</small></span></label>)}
      </div>
      <h3 className="settings-subheading">Message templates</h3>
      <div className="template-picker" role="tablist" aria-label="SMS event templates">
        {Object.keys(smsTemplateDefaults).map((name) => <button key={name} role="tab" aria-selected={activeTemplate === name} className={activeTemplate === name ? "active" : ""} onClick={() => setActiveTemplate(name)}>{name}</button>)}
      </div>
      <label className="template-editor">{activeTemplate}<textarea value={template} onChange={(event) => setTemplate(event.target.value)} rows={4} /></label>
      <div className="template-tokens">{["{{side}}", "{{price}}", "{{qty}}", "{{pnl}}", "{{reason}}", "{{weight}}", "{{environment}}"].map((token) => <button key={token} onClick={() => setTemplate((value) => `${value} ${token}`)}>{token}</button>)}</div>
      <div className="credential-footer"><button className="button secondary" onClick={() => showToast("Test SMS queued", "notify.lk accepted the prototype message; an audit event was written.")}><Send size={14} />Send test SMS</button><span>Last delivery: 20:00 UTC · 1.8s</span></div>
    </Panel>
  );
}

function NewsSettings({ showToast }) {
  const [enabled, setEnabled] = useState(true);
  return (
    <Panel className="settings-card">
      <SettingsHeading icon={Newspaper} kicker="ISOLATED READ-ONLY SERVICE" title="News agent" description="Collect, deduplicate, summarize and publish. No trading permissions." status="Healthy" />
      <div className="setting-row"><span><strong>Daily briefing</strong><small>Scheduled collection and publication</small></span><button className={`toggle ${enabled ? "on" : ""}`} role="switch" aria-checked={enabled} onClick={() => setEnabled((value) => !value)}><i /></button></div>
      <div className="form-grid two">
        <label>Local briefing time<input type="time" defaultValue="06:30" /></label>
        <label>Summary model<select defaultValue="claude-haiku-4-5"><option value="claude-haiku-4-5">Claude Haiku 4.5</option><option value="claude-sonnet-5">Claude Sonnet 5</option></select></label>
      </div>
      <h3 className="settings-subheading">Sources</h3>
      <div className="notification-toggle-grid">
        {["CoinDesk RSS", "Cointelegraph RSS", "Bitcoin Magazine", "Macro headlines", "FOMC / CPI calendar"].map((item) => <label key={item}><input type="checkbox" defaultChecked /><span><strong>{item}</strong><small>URL-unique collection</small></span></label>)}
      </div>
      <div className="ai-boundary"><ShieldCheck size={18} /><div><strong>Permission boundary</strong><p>No Binance keys, no execution API, no strategy imports and no signal-gating capability.</p></div></div>
      <button className="button secondary" onClick={() => showToast("Briefing refresh started", "Collecting configured sources and deduplicating URLs.")}><RefreshCw size={14} />Refresh now</button>
    </Panel>
  );
}

function SecuritySettings({ showToast, openModal }) {
  return (
    <Panel className="settings-card">
      <SettingsHeading icon={ShieldCheck} kicker="OWNER ACCESS" title="Security & sessions" description="JWT session, Argon2 password hashing and owner-configurable SMS verification." status="SMS 2FA on" />
      <div className="security-list">
        <div><span className="settings-icon"><Smartphone size={18} /></span><span><strong>SMS two-factor</strong><small>Sign-in requires a single-use SMS code while enabled. Recovery is server-shell only.</small></span><button className="button secondary" onClick={() => showToast("Number change protected", "Changing the number requires password re-entry and a code sent to the new phone.")}>Change number</button></div>
        <div><span className="settings-icon"><Clock3 size={18} /></span><span><strong>Session timeout</strong><small>Automatically revoke an inactive owner session.</small></span><select defaultValue="30"><option value="15">15 minutes</option><option value="30">30 minutes</option><option value="60">1 hour</option></select></div>
        <div><span className="settings-icon"><ShieldCheck size={18} /></span><span><strong>TLS and host hardening</strong><small>Caddy TLS, non-root containers, firewall, fail2ban and unattended security updates.</small></span><StatusPill tone="success">Compliant</StatusPill></div>
        <div><span className="settings-icon"><Archive size={18} /></span><span><strong>Nightly encrypted backup</strong><small>Last pg_dump verified at 02:10 UTC. Restore drill passed 01 Jul.</small></span><StatusPill tone="success">Healthy</StatusPill></div>
      </div>
      <div className="danger-zone"><div><strong>Sign out all other sessions</strong><p>Revokes every owner JWT session except this one and writes a security event.</p></div><button className="button danger" onClick={() => openModal({ tone: "danger", icon: LogOut, kicker: "SESSION REVOCATION", title: "Sign out all other sessions?", body: "Other browser sessions will immediately lose access. This current session remains active.", confirmLabel: "Revoke other sessions", onConfirm: () => showToast("Other sessions revoked", "A security audit event was written.") })}>Revoke others</button></div>
    </Panel>
  );
}

function OperationsSettings({ showToast }) {
  return (
    <div className="view-stack">
      <Panel className="settings-card">
        <SettingsHeading icon={Activity} kicker="DEPLOYMENT HEALTH" title="Runtime & recovery" description="Docker services, scheduler, exchange connection and backup controls." status="All healthy" />
        <div className="operations-grid">
          <span><Server size={18} /><div><small>FastAPI + bot</small><strong>Healthy · uptime 19d</strong></div><StatusPill tone="success">Running</StatusPill></span>
          <span><Database size={18} /><div><small>PostgreSQL 16</small><strong>8 ms · 3.8 GB</strong></div><StatusPill tone="success">Synced</StatusPill></span>
          <span><Cloud size={18} /><div><small>Caddy / TLS</small><strong>Certificate 71d left</strong></div><StatusPill tone="success">Secure</StatusPill></span>
          <span><HardDrive size={18} /><div><small>Encrypted backup</small><strong>02:10 UTC · verified</strong></div><StatusPill tone="success">Current</StatusPill></span>
          <span><RadioTower size={18} /><div><small>Dead-man cron</small><strong>Last tick 00:00 UTC</strong></div><StatusPill tone="success">Armed</StatusPill></span>
          <span><Wifi size={18} /><div><small>REST + WebSocket</small><strong>Connected · backoff idle</strong></div><StatusPill tone="success">Online</StatusPill></span>
        </div>
      </Panel>
      <Panel className="settings-card">
        <SettingsHeading icon={TestTube2} kicker="ROLLOUT GATE" title="DEMO acceptance progress" description="LIVE remains blocked until the documented four-week criteria pass." status="Day 19 of 28" />
        <div className="rollout-timeline">
          <span className="done"><i><Check size={13} /></i><div><strong>Parity replay</strong><small>Zero decision mismatches · all tests green</small></div></span>
          <span className="active"><i>2</i><div><strong>DEMO dry-run</strong><small>19 days · all trades explained · forced failures passing</small></div></span>
          <span><i>3</i><div><strong>LIVE pilot</strong><small>Locked · minimum size after owner sign-off</small></div></span>
          <span><i>4</i><div><strong>Full operation</strong><small>Monthly review against Appendix A expectations</small></div></span>
        </div>
      </Panel>
      <Panel className="settings-card">
        <SettingsHeading icon={ShieldAlert} kicker="FAILURE DRILLS" title="Acceptance evidence" description="Network cuts, restarts and safety controls are rehearsed before LIVE." />
        <div className="drill-list">
          <span><CheckCircle2 size={16} /><div><strong>Restart mid-trade</strong><small>Persisted state resumed and Binance reconciled before action.</small></div><time>12 Jul</time></span>
          <span><CheckCircle2 size={16} /><div><strong>WebSocket disconnect</strong><small>REST backfill and missed-candle catch-up completed.</small></div><time>13 Jul</time></span>
          <span><CheckCircle2 size={16} /><div><strong>Kill switch</strong><small>Orders cancelled, position flattened and SMS delivered in 18s.</small></div><time>15 Jul</time></span>
          <span><CheckCircle2 size={16} /><div><strong>Breaker trigger</strong><small>Long and short sides halted independently until month reset.</small></div><time>16 Jul</time></span>
        </div>
        <button className="button secondary" onClick={() => showToast("Health check requested", "All prototype services report healthy.")}><RefreshCw size={14} />Run health check</button>
      </Panel>
    </div>
  );
}

function ConfirmationModal({ modal, setModal }) {
  const [confirmation, setConfirmation] = useState("");
  const Icon = modal.icon || AlertTriangle;
  const requiresWord = Boolean(modal.confirmWord);
  const canConfirm = !requiresWord || confirmation === modal.confirmWord;
  const close = () => setModal(null);
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && close()}>
      <section className={`modal ${modal.tone || "warning"}`} role="dialog" aria-modal="true" aria-labelledby="modal-title">
        <IconButton label="Close dialog" className="modal-close" onClick={close}><X size={17} /></IconButton>
        <span className="modal-icon"><Icon size={22} /></span>
        <p className="kicker">{modal.kicker || "CONFIRM ACTION"}</p>
        <h1 id="modal-title">{modal.title}</h1>
        <p>{modal.body}</p>
        {modal.details && <ul>{modal.details.map((item) => <li key={item}><Check size={14} />{item}</li>)}</ul>}
        {requiresWord && <label className="confirm-field">Type <strong>{modal.confirmWord}</strong> to confirm<input aria-label={`Type ${modal.confirmWord} to confirm`} value={confirmation} onChange={(event) => setConfirmation(event.target.value)} autoFocus /></label>}
        <div className="modal-actions">
          <button className="button ghost" onClick={close}>Cancel</button>
          <button className={`button ${modal.tone === "danger" ? "danger" : "primary"}`} disabled={!canConfirm} onClick={() => { modal.onConfirm?.(); close(); }}>{modal.confirmLabel || "Confirm"}</button>
        </div>
        {modal.footnote && <small className="modal-footnote">{modal.footnote}</small>}
      </section>
    </div>
  );
}

export function App() {
  const [authStage, setAuthStage] = useState("login");
  const [activeView, setActiveView] = useState("overview");
  const [settingsTab, setSettingsTab] = useState("environment");
  const [mobileOpen, setMobileOpen] = useState(false);
  const [notificationOpen, setNotificationOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [botRunning, setBotRunning] = useState(true);
  const [safeMode, setSafeMode] = useState(false);
  const [environment, setEnvironment] = useState("DEMO");
  const [modal, setModal] = useState(null);
  const [toast, setToast] = useState(null);
  const [selectedTrade, setSelectedTrade] = useState(null);
  const [withdrawn, setWithdrawn] = useState(false);

  const showToast = (title, message) => {
    setToast({ title, message });
    window.clearTimeout(window.__cryptopilotToast);
    window.__cryptopilotToast = window.setTimeout(() => setToast(null), 4200);
  };

  useEffect(() => {
    const handleEscape = (event) => {
      if (event.key !== "Escape") return;
      setModal(null);
      setSelectedTrade(null);
      setNotificationOpen(false);
      setProfileOpen(false);
      setMobileOpen(false);
    };
    document.addEventListener("keydown", handleEscape);
    return () => document.removeEventListener("keydown", handleEscape);
  }, []);

  if (authStage === "login") return <Login onContinue={() => setAuthStage("otp")} />;
  if (authStage === "otp") return <Otp onVerify={() => setAuthStage("app")} onBack={() => setAuthStage("login")} />;

  const signOut = () => {
    setAuthStage("login");
    setProfileOpen(false);
    setNotificationOpen(false);
  };

  const botAction = () => {
    if (botRunning) {
      setModal({
        tone: "warning",
        icon: Square,
        kicker: "SAFE STOP",
        title: "Stop evaluation and leave the position open?",
        body: "CryptoPilot will stop evaluating new candles. The current stop-free short remains exposed if it is left open.",
        details: ["No new candle decisions", "Existing position remains on Binance", "SMS and audit event created"],
        confirmLabel: "Stop, leave position",
        onConfirm: () => {
          setBotRunning(false);
          setSafeMode(false);
          showToast("Bot stopped safely", "The short position remains open; an SMS and audit event were created.");
        },
      });
    } else {
      setModal({
        tone: "warning",
        icon: Play,
        kicker: "RECONCILE & START",
        title: `Start on ${environment}?`,
        body: "CryptoPilot will connect to Binance, compare account truth with persisted state and catch up any missed closed candles before starting the 24/7 loop.",
        details: ["No action before reconciliation", "Mismatch enters safe mode", "Next decision only at a closed 4h candle"],
        confirmLabel: "Reconcile & start",
        onConfirm: () => {
          setBotRunning(true);
          setSafeMode(false);
          showToast("Bot started safely", `${environment} reconciled. The loop is waiting for the next 4h close.`);
        },
      });
    }
  };

  const killSwitch = () => setModal({
    tone: "danger",
    icon: OctagonAlert,
    kicker: `${environment} EMERGENCY CONTROL`,
    title: "Flatten everything and stop?",
    body: "This immediately cancels all open orders, flattens every position at market, stops evaluation, sends SMS and writes the complete audit sequence.",
    confirmWord: "FLATTEN",
    confirmLabel: "Flatten & stop",
    footnote: "Market slippage is possible. This action cannot be undone.",
    onConfirm: () => {
      setBotRunning(false);
      setSafeMode(false);
      showToast("Kill switch activated", "Orders cancelled, positions flattening, bot stopped and emergency SMS queued.");
    },
  });

  const stopAndClose = () => setModal({
    tone: "danger",
    icon: OctagonAlert,
    kicker: "STOP & CLOSE",
    title: "Flatten the position, then stop?",
    body: "CryptoPilot will submit a reduce-only MARKET cover for the 0.142 BTC short, confirm the Binance fill, then stop the execution loop.",
    details: ["Cancel resting orders", "Flatten the short at market", "Reconcile the fill", "Send SMS and write audit events"],
    confirmLabel: "Close position & stop",
    onConfirm: () => {
      setBotRunning(false);
      setSafeMode(false);
      showToast("Position closing", "Reduce-only cover submitted; the bot stops after Binance confirms the fill.");
    },
  });

  const enterSafeMode = () => {
    setSafeMode(true);
    showToast("Safe mode enabled", "New entries are blocked; existing position management and reconciliation continue.");
  };

  const exportAction = (type) => {
    if (type === "refresh-news") {
      showToast("Briefing refresh started", "Collecting configured sources and deduplicating URLs.");
      return;
    }
    const content = type === "trades"
      ? `trade_id,side,environment,strategy,realized_pnl\n${tradeRows.map((trade) => `${trade.id},${trade.side},${trade.environment},${trade.strategy},${trade.pnl}`).join("\n")}`
      : type === "monthly"
        ? `month,trades,realized_pnl,fees,withdrawn,net\n${monthlyRows.map((row) => row.slice(0, 6).join(",")).join("\n")}`
        : JSON.stringify(eventRows, null, 2);
    const blob = new Blob([content], { type: type === "events" ? "application/json" : "text/csv" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `cryptopilot-${type}.${type === "events" ? "json" : "csv"}`;
    anchor.click();
    URL.revokeObjectURL(url);
    showToast("Export prepared", `CryptoPilot ${type} export is ready.`);
  };

  return (
    <div className="app-shell">
      <Sidebar activeView={activeView} setActiveView={setActiveView} mobileOpen={mobileOpen} setMobileOpen={setMobileOpen} onSignOut={signOut} />
      <div className="main-shell">
        <Header environment={environment} setMobileOpen={setMobileOpen} notificationOpen={notificationOpen} setNotificationOpen={setNotificationOpen} profileOpen={profileOpen} setProfileOpen={setProfileOpen} onSignOut={signOut} />
        <main className="content">
          <PageHeading activeView={activeView} botRunning={botRunning} safeMode={safeMode} onBotAction={botAction} onStopClose={stopAndClose} onSafeMode={enterSafeMode} onKill={killSwitch} onExport={exportAction} />
          {activeView === "overview" && <Overview setActiveView={setActiveView} setSettingsTab={setSettingsTab} showToast={showToast} />}
          {activeView === "trades" && <Trades selectedTrade={selectedTrade} setSelectedTrade={setSelectedTrade} />}
          {activeView === "monthly" && <Monthly withdrawn={withdrawn} onMarkWithdrawn={() => setModal({ tone: "warning", icon: Wallet, kicker: "MANUAL BOOKKEEPING", title: "Mark $34.37 as withdrawn?", body: "This records an owner action in the monthly ledger. CryptoPilot does not move funds or call a withdrawal API.", confirmLabel: "Mark withdrawn", onConfirm: () => { setWithdrawn(true); showToast("Withdrawal marked", "July ledger updated; no funds were moved."); } })} />}
          {activeView === "news" && <News showToast={showToast} />}
          {activeView === "events" && <Events />}
          {activeView === "settings" && <SettingsView environment={environment} setEnvironment={setEnvironment} botRunning={botRunning} settingsTab={settingsTab} setSettingsTab={setSettingsTab} showToast={showToast} openModal={setModal} />}
        </main>
      </div>
      {modal && <ConfirmationModal modal={modal} setModal={setModal} />}
      {toast && <div className="toast" role="status"><CheckCircle2 size={18} /><span><strong>{toast.title}</strong><small>{toast.message}</small></span></div>}
    </div>
  );
}
