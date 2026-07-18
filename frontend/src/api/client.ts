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
  { auth = true }: { auth?: boolean } = {},
): Promise<T> {
  let resp = await rawRequest(path, init, auth);
  if (resp.status === 401 && auth) {
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

export function login(email: string, password: string): Promise<{ totp_token: string }> {
  return apiRequest(
    "/api/auth/login",
    { method: "POST", body: JSON.stringify({ email, password }) },
    { auth: false },
  );
}

export function verifyTotp(totpToken: string, code: string): Promise<Tokens> {
  return apiRequest(
    "/api/auth/totp",
    {
      method: "POST",
      body: JSON.stringify({ code }),
      headers: { Authorization: `Bearer ${totpToken}` },
    },
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
}): Promise<{ message: string }> {
  return apiRequest("/api/settings/credentials", {
    method: "PUT",
    body: JSON.stringify(body),
  });
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
