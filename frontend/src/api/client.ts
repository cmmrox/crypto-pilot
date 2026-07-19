/**
 * Typed API client with automatic access-token refresh.
 * Tokens live in sessionStorage (survive reload, cleared on sign-out).
 */

export interface Health {
  status: string;
  version: string;
  database: string;
}

export interface Tokens {
  access_token: string;
  refresh_token: string;
}

export interface Me {
  email: string;
  role: string;
}

const BASE = import.meta.env.VITE_API_BASE ?? "";
const ACCESS_KEY = "cp_access";
const REFRESH_KEY = "cp_refresh";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

function getAccess(): string | null {
  return sessionStorage.getItem(ACCESS_KEY);
}
function getRefresh(): string | null {
  return sessionStorage.getItem(REFRESH_KEY);
}
export function setTokens(t: Tokens): void {
  sessionStorage.setItem(ACCESS_KEY, t.access_token);
  sessionStorage.setItem(REFRESH_KEY, t.refresh_token);
}
export function clearTokens(): void {
  sessionStorage.removeItem(ACCESS_KEY);
  sessionStorage.removeItem(REFRESH_KEY);
}
export function hasSession(): boolean {
  return getAccess() !== null;
}

// The store registers a handler so a dead session (refresh failed on an
// authenticated call) immediately forces the UI back to the login screen.
let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(handler: () => void): void {
  onUnauthorized = handler;
}

async function rawRequest(path: string, init: RequestInit, withAuth: boolean): Promise<Response> {
  const headers = new Headers(init.headers);
  if (init.body) headers.set("Content-Type", "application/json");
  if (withAuth) {
    const token = getAccess();
    if (token) headers.set("Authorization", `Bearer ${token}`);
  }
  return fetch(`${BASE}${path}`, { ...init, headers });
}

async function tryRefresh(): Promise<boolean> {
  const refresh = getRefresh();
  if (!refresh) return false;
  const resp = await rawRequest(
    "/api/auth/refresh",
    { method: "POST", body: JSON.stringify({ refresh_token: refresh }) },
    false,
  );
  if (!resp.ok) return false;
  setTokens((await resp.json()) as Tokens);
  return true;
}

/** Authenticated request with one transparent refresh-and-retry on 401. */
export async function apiRequest<T>(
  path: string,
  init: RequestInit = {},
  {
    auth = true,
    refreshOnUnauthorized = true,
  }: { auth?: boolean; refreshOnUnauthorized?: boolean } = {},
): Promise<T> {
  let resp = await rawRequest(path, init, auth);
  if (resp.status === 401 && auth && refreshOnUnauthorized) {
    if (await tryRefresh()) {
      resp = await rawRequest(path, init, auth);
    }
    // Still unauthorized after a refresh attempt → the session is dead.
    if (resp.status === 401) {
      clearTokens();
      onUnauthorized?.();
    }
  }
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      detail = typeof body.detail === "string" ? body.detail : detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(resp.status, detail);
  }
  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

// --- Endpoints ---

export function getHealth(): Promise<Health> {
  return apiRequest<Health>("/health", {}, { auth: false });
}

export interface DeepHealth {
  status: string;
  version: string;
  database: string;
  ingest_last_tick: string | null;
  ingest_overdue: boolean;
  scheduler_alive: boolean;
}

export const getDeepHealth = () => apiRequest<DeepHealth>("/health/deep", {}, { auth: false });

export interface LoginResponse {
  mode: "tokens" | "otp";
  access_token: string | null;
  refresh_token: string | null;
  otp_token: string | null;
  phone_hint: string | null;
}

export function login(email: string, password: string): Promise<LoginResponse> {
  return apiRequest(
    "/api/auth/login",
    { method: "POST", body: JSON.stringify({ email, password }) },
    { auth: false },
  );
}

export function verifyOtp(otpToken: string, code: string): Promise<Tokens> {
  return apiRequest(
    "/api/auth/otp/verify",
    {
      method: "POST",
      body: JSON.stringify({ code }),
      headers: { Authorization: `Bearer ${otpToken}` },
    },
    { auth: false },
  );
}

export function resendOtp(otpToken: string): Promise<{ message: string }> {
  return apiRequest(
    "/api/auth/otp/resend",
    { method: "POST", headers: { Authorization: `Bearer ${otpToken}` } },
    { auth: false },
  );
}

export function getMe(): Promise<Me> {
  return apiRequest<Me>("/api/auth/me");
}

export async function logout(): Promise<void> {
  try {
    await apiRequest("/api/auth/logout", { method: "POST" });
  } finally {
    clearTokens();
  }
}

// --- Events ---

export interface EventRow {
  id: number;
  ts: string;
  level: string;
  category: string;
  message: string;
  payload_json: Record<string, unknown>;
  sms_status: string | null;
  ref: string | null;
}

export function getEvents(params: {
  level?: string;
  category?: string;
  search?: string;
  limit?: number;
}): Promise<EventRow[]> {
  const q = new URLSearchParams();
  if (params.level) q.set("level", params.level);
  if (params.category) q.set("category", params.category);
  if (params.search) q.set("search", params.search);
  q.set("limit", String(params.limit ?? 100));
  return apiRequest<EventRow[]>(`/api/events?${q.toString()}`);
}

// --- Market / connection ---

export interface MarketStatus {
  symbol: string;
  interval: string;
  environment: string;
  candles_stored: number;
  latest_open_time: string | null;
  gaps: number;
  next_close_utc: string;
  seconds_to_next_close: number;
  clock_drift_ms: number | null;
  exchange_reachable: boolean;
}

export function getMarketStatus(): Promise<MarketStatus> {
  return apiRequest<MarketStatus>("/api/market/status");
}

export function backfillCandles(): Promise<MarketStatus> {
  return apiRequest<MarketStatus>("/api/market/backfill", { method: "POST" });
}

// --- Credentials ---

export interface CredentialStatus {
  service: string;
  environment: string;
  configured: boolean;
  key_hint: string | null;
}

export function getCredentialStatus(
  environment: string,
  service: string,
): Promise<CredentialStatus> {
  return apiRequest<CredentialStatus>(`/api/settings/credentials/${environment}/${service}`);
}

export function saveCredential(body: {
  environment: string;
  service: string;
  api_key: string;
  api_secret: string;
  current_password: string;
}): Promise<{ message: string }> {
  return apiRequest(
    "/api/settings/credentials",
    {
      method: "PUT",
      body: JSON.stringify(body),
    },
    { refreshOnUnauthorized: false },
  );
}

export function testBinanceConnection(
  environment: string,
): Promise<{ ok: boolean; detail: string }> {
  return apiRequest(`/api/settings/credentials/${environment}/binance/test`, {
    method: "POST",
  });
}

// --- Strategies ---

export interface StrategyInfo {
  name: string;
  validated_release: string;
  direction: string;
  warmup_bars: number;
  params: Record<string, number>;
  parity_verified: boolean;
  active: boolean;
}

export function getStrategies(): Promise<StrategyInfo[]> {
  return apiRequest<StrategyInfo[]>("/api/strategies");
}

// --- Bot + Overview ---

export interface BotStatus {
  status: string;
  environment: string;
  strategy: string;
  run_id: number | null;
  started_at: string | null;
  safe_mode_reason: string | null;
}

export interface Position {
  side: string | null;
  qty: string;
  entry_price: string;
  mark_price: string;
  unrealized_pnl: string;
  leverage: string;
  has_price_stop: boolean;
}

export interface Breaker {
  book: string;
  month_to_date_pnl: string;
  drawdown_pct: string;
  tripped: boolean;
}

export interface Overview {
  environment: string;
  bot_status: string;
  strategy: string;
  exchange_reachable: boolean;
  balance: string;
  equity: string;
  unrealized_pnl: string;
  position: Position | null;
  breakers: Breaker[];
  month_realized_pnl: string;
}

export interface EquityPoint {
  ts: string;
  equity: string;
}

export const getOverview = () => apiRequest<Overview>("/api/overview");
export const getEquityCurve = () => apiRequest<EquityPoint[]>("/api/overview/equity");
export const getBotStatus = () => apiRequest<BotStatus>("/api/bot/status");
export const startBot = () => apiRequest<{ message: string }>("/api/bot/start", { method: "POST" });
export const stopBot = () => apiRequest<{ message: string }>("/api/bot/stop", { method: "POST" });
export const stopCloseBot = () =>
  apiRequest<{ message: string }>("/api/bot/stop-close", { method: "POST" });
export const safeModeBot = () =>
  apiRequest<{ message: string }>("/api/bot/safe-mode", { method: "POST" });
export const killSwitch = () => apiRequest<{ ok: boolean }>("/api/ops/kill", { method: "POST" });

// --- Trades ---

export interface TradeRow {
  id: number;
  opened_at: string;
  closed_at: string | null;
  side: string;
  entry_px: string;
  exit_px: string | null;
  qty: string;
  fees: string;
  realized_pnl: string | null;
  r_multiple: string | null;
  exit_reason: string | null;
  strategy: string;
  environment: string;
  outcome: string;
}

export interface OrderRow {
  client_order_id: string;
  binance_order_id: string | null;
  type: string;
  status: string;
  qty: string;
  price: string | null;
  stop_price: string | null;
  reduce_only: boolean;
}

export interface TradeDetail extends TradeRow {
  orders: OrderRow[];
}

export interface TradeFilters {
  side?: string;
  environment?: string;
  strategy?: string;
  month?: string;
  search?: string;
}

function tradeQuery(f: TradeFilters): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(f)) if (v) q.set(k, v);
  return q.toString();
}

export const getTrades = (f: TradeFilters = {}) =>
  apiRequest<TradeRow[]>(`/api/trades?${tradeQuery(f)}`);
export const getTradeDetail = (id: number) => apiRequest<TradeDetail>(`/api/trades/${id}`);

/** Fetch the trades CSV as text with auth (endpoint requires a bearer token). */
export async function getTradesCsv(f: TradeFilters = {}): Promise<string> {
  let resp = await rawRequest(`/api/trades/export.csv?${tradeQuery(f)}`, {}, true);
  if (resp.status === 401 && (await tryRefresh())) {
    resp = await rawRequest(`/api/trades/export.csv?${tradeQuery(f)}`, {}, true);
  }
  if (!resp.ok) throw new ApiError(resp.status, "csv export failed");
  return resp.text();
}

// --- Monthly ---

export interface MonthRow {
  month: string;
  trades: number;
  realized_pnl: string;
  fees: string;
  net: string;
  withdrawn: string;
  withdrawable: string;
  long_breaker: string;
  short_breaker: string;
}

export const getMonthly = () => apiRequest<MonthRow[]>("/api/monthly");
export const markWithdrawn = (month: string) =>
  apiRequest<{ message: string }>("/api/monthly/mark-withdrawn", {
    method: "POST",
    body: JSON.stringify({ month }),
  });

// --- SMS (notify.lk) ---

export interface SmsStatus {
  configured: boolean;
  sender_id: string | null;
  phone_hint: string | null;
  sms_enabled: boolean;
}

export const getSmsStatus = () => apiRequest<SmsStatus>("/api/settings/sms");
export const saveSmsConfig = (body: {
  user_id: string;
  api_key: string;
  sender_id: string;
  phone: string;
  current_password: string;
}) =>
  apiRequest<{ message: string }>(
    "/api/settings/sms",
    {
      method: "PUT",
      body: JSON.stringify(body),
    },
    { refreshOnUnauthorized: false },
  );
export const toggleSms = (enabled: boolean) =>
  apiRequest<{ message: string }>("/api/settings/sms/toggle", {
    method: "POST",
    body: JSON.stringify({ enabled }),
  });
export const testSms = () =>
  apiRequest<{ ok: boolean; detail: string }>("/api/settings/sms/test", { method: "POST" });

// --- News + Codex ---

export interface NewsBriefing {
  briefing_date: string | null;
  model: string | null;
  sentiment: string | null;
  bullets: { text: string; source: string }[];
  generated_at: string | null;
  macro_calendar: { date: string; event: string; impact: string }[];
  isolation_notice: string;
}

export interface ArchiveItem {
  briefing_date: string;
  sentiment: string | null;
  model: string | null;
}

export const getLatestBriefing = () => apiRequest<NewsBriefing>("/api/news/latest");
export const getNewsArchive = () => apiRequest<ArchiveItem[]>("/api/news/archive");
export const refreshBriefing = () =>
  apiRequest<{ ok: boolean; detail: string }>("/api/news/refresh", { method: "POST" });

export interface CodexLoginStart {
  login_id: string;
  verification_url: string;
  user_code: string;
}

export const getCodexStatus = () =>
  apiRequest<{ authenticated: boolean }>("/api/settings/codex/status");
export const startCodexLogin = () =>
  apiRequest<CodexLoginStart>("/api/settings/codex/login", { method: "POST" });
export const getCodexLoginStatus = (loginId: string) =>
  apiRequest<{ status: string; detail: string }>(`/api/settings/codex/login/${loginId}`);
export const codexLogout = () =>
  apiRequest<{ message: string }>("/api/settings/codex/logout", { method: "POST" });

// --- Guarded settings ---

export const switchEnvironment = (environment: string, confirm?: string) =>
  apiRequest<{ message: string }>("/api/settings/environment", {
    method: "PUT",
    body: JSON.stringify({ environment, confirm }),
  });
export const switchStrategy = (name: string) =>
  apiRequest<{ message: string }>("/api/settings/strategy", {
    method: "PUT",
    body: JSON.stringify({ name }),
  });

// --- Two-factor authentication (SMS) ---

export interface SecurityStatus {
  twofa_enabled: boolean;
  phone_hint: string | null;
}

export type SecurityAction = "enable" | "disable" | "change_phone";

export const getSecurityStatus = () => apiRequest<SecurityStatus>("/api/settings/security");

export const startSecurityChange = (body: {
  password: string;
  action: SecurityAction;
  new_phone?: string;
}) =>
  apiRequest<{ challenge_id: number; phone_hint: string | null }>(
    "/api/settings/security/2fa/start",
    { method: "POST", body: JSON.stringify(body) },
    { refreshOnUnauthorized: false },
  );

export const confirmSecurityChange = (challengeId: number, code: string) =>
  apiRequest<{ message: string }>(
    "/api/settings/security/2fa/confirm",
    {
      method: "POST",
      body: JSON.stringify({ challenge_id: challengeId, code }),
    },
    { refreshOnUnauthorized: false },
  );
