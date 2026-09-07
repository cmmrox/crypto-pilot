import { useEffect, useState } from "react";
import {
  Bot,
  CheckCircle2,
  Copy,
  ExternalLink,
  KeyRound,
  Lock,
  MessageSquareText,
  PlugZap,
  Send,
  ShieldCheck,
  Smartphone,
  Waypoints,
} from "lucide-react";
import {
  ApiError,
  codexLogout,
  confirmSecurityChange,
  getBotStatus,
  getCodexLoginStatus,
  getCodexStatus,
  getCredentialStatus,
  getSecurityStatus,
  getSmsStatus,
  getStrategies,
  saveCredential,
  saveSmsConfig,
  startCodexLogin,
  startSecurityChange,
  switchEnvironment,
  switchStrategy,
  testBinanceConnection,
  testSms,
  toggleSms,
  type CodexLoginStart,
  type CredentialStatus,
  type SecurityAction,
  type SecurityStatus,
  type SmsStatus,
  type StrategyInfo,
} from "../api/client";
import { ConfirmModal, type ModalSpec } from "../components/ConfirmModal";
import { Activity, Database, RadioTower, RefreshCw, Server, Wifi } from "lucide-react";
import { getDeepHealth, type DeepHealth } from "../api/client";
import { LoadingState, Spinner } from "../components/AsyncState";

/** Stage 2 Settings: Binance API credentials (write-only) + connection test. */
export function Settings() {
  return (
    <div className="view-stack">
      <div className="page-heading">
        <div>
          <p className="kicker">SECURITY & CONFIGURATION</p>
          <h1 data-testid="view-title">Settings</h1>
          <p>API credentials are write-only and encrypted at rest (AES-GCM).</p>
        </div>
      </div>
      <SecurityCard />
      <EnvironmentCard />
      <StrategyLibrary />
      <CodexCard />
      <CredentialCard environment="DEMO" />
      <CredentialCard environment="LIVE" />
      <SmsCard />
      <OperationsCard />
      <div className="panel key-permissions">
        <div className="settings-heading">
          <span className="settings-icon">
            <ShieldCheck size={18} />
          </span>
          <div>
            <p className="kicker">KEY PERMISSIONS</p>
            <h2>Required account controls</h2>
            <p>The production backend rejects unsafe exchange credentials.</p>
          </div>
        </div>
        <div className="permission-grid">
          {[
            "Futures trading enabled",
            "Read access enabled",
            "Withdrawals disabled",
            "IP allowlisted to the VPS",
            "Isolated margin",
            "One-way position mode",
          ].map((p) => (
            <span key={p}>
              <CheckCircle2 size={14} />
              {p}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

function SecurityCard() {
  const [status, setStatus] = useState<SecurityStatus | null>(null);
  const [statusLoading, setStatusLoading] = useState(true);
  // Active guarded flow: null when idle, otherwise the pending action.
  const [action, setAction] = useState<SecurityAction | null>(null);
  const [password, setPassword] = useState("");
  const [newPhone, setNewPhone] = useState("");
  const [challengeId, setChallengeId] = useState<number | null>(null);
  const [code, setCode] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [guard, setGuard] = useState<ModalSpec | null>(null);

  const refresh = async () => {
    setStatusLoading(true);
    try {
      setStatus(await getSecurityStatus());
    } catch {
      setStatus(null);
      setMsg({ ok: false, text: "Could not load account security status." });
    } finally {
      setStatusLoading(false);
    }
  };
  useEffect(() => {
    void refresh();
  }, []);

  const reset = () => {
    setAction(null);
    setPassword("");
    setNewPhone("");
    setChallengeId(null);
    setCode("");
  };

  const begin = (next: SecurityAction) => {
    reset();
    setMsg(null);
    setAction(next);
  };

  const requestToggle = () => {
    if (!status) return;
    if (!status.twofa_enabled) {
      begin("enable");
      return;
    }
    setGuard({
      tone: "danger",
      kicker: "REDUCE ACCOUNT SECURITY",
      title: "Disable two-factor authentication?",
      body: "Future sign-ins will use the owner password only.",
      details: [
        "A verification code will be sent to the current mobile number.",
        "All other signed-in sessions will be revoked after confirmation.",
        "The previous number receives a security notification.",
      ],
      confirmLabel: "Continue to verification",
      onConfirm: () => begin("disable"),
    });
  };

  const sendCode = async () => {
    if (!action) return;
    if (!password) {
      setMsg({ ok: false, text: "Enter your current password." });
      return;
    }
    if ((action === "enable" || action === "change_phone") && !/^94[0-9]{9}$/.test(newPhone)) {
      setMsg({ ok: false, text: "Enter a valid mobile number (9471XXXXXXX)." });
      return;
    }
    setBusy(true);
    setMsg(null);
    try {
      const res = await startSecurityChange({
        password,
        action,
        new_phone: action === "disable" ? undefined : newPhone,
      });
      setPassword("");
      setChallengeId(res.challenge_id);
      setMsg({
        ok: true,
        text: `Verification code sent${res.phone_hint ? ` to ${res.phone_hint}` : ""}.`,
      });
    } catch (err) {
      const detail = err instanceof ApiError ? err.message : "Could not start the change.";
      setMsg({ ok: false, text: detail });
    } finally {
      setBusy(false);
    }
  };

  const confirm = async () => {
    if (!challengeId || code.length !== 6) {
      setMsg({ ok: false, text: "Enter the 6-digit code from the SMS." });
      return;
    }
    setBusy(true);
    try {
      const res = await confirmSecurityChange(challengeId, code);
      setMsg({ ok: true, text: res.message });
      reset();
      await refresh();
    } catch (err) {
      const detail = err instanceof ApiError ? err.message : "That code was not accepted.";
      setMsg({ ok: false, text: detail });
    } finally {
      setBusy(false);
    }
  };

  const enabled = status?.twofa_enabled ?? false;

  return (
    <div className="panel credential-card" data-testid="twofa-card">
      <div className="settings-heading">
        <span className="settings-icon">
          <Lock size={18} />
        </span>
        <div>
          <p className="kicker">ACCOUNT SECURITY</p>
          <h2>Two-factor authentication</h2>
          <p>A one-time SMS code is required at sign-in while this is on.</p>
        </div>
        <span className={`pill ${enabled ? "ok" : "warn"}`} data-testid="twofa-state">
          {statusLoading ? <><Spinner size={12} /> Checking…</> : status === null ? "Unavailable" : enabled ? `On ${status.phone_hint ?? ""}` : "Off"}
        </span>
      </div>

      <div className="setting-row">
        <span>
          <strong>SMS two-factor</strong>
          <small>
            {enabled
              ? "Sign-in requires your password and an SMS code."
              : "Sign-in uses your password only. Turn on for stronger protection."}
          </small>
        </span>
        <button
          className={`toggle ${enabled ? "on" : ""}`}
          role="switch"
          aria-checked={enabled}
          aria-label="Toggle two-factor authentication"
          data-testid="twofa-toggle"
          onClick={requestToggle}
          disabled={!status || busy}
        >
          <i />
        </button>
      </div>

      {enabled && action === null && (
        <div className="credential-footer">
          <button
            className="button secondary"
            data-testid="twofa-change-phone"
            onClick={() => begin("change_phone")}
          >
            <Smartphone size={14} /> Change mobile number
          </button>
        </div>
      )}

      {action !== null && (
        <div className="twofa-flow" data-testid="twofa-flow">
          <p className="kicker">
            {action === "enable"
              ? "ENABLE TWO-FACTOR"
              : action === "disable"
                ? "DISABLE TWO-FACTOR"
                : "CHANGE MOBILE NUMBER"}
          </p>
          {challengeId === null ? (
            <>
              <div className="form-grid">
                <label>
                  Current password
                  <input
                    type="password"
                    aria-label="Current password"
                    autoComplete="current-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                </label>
                {(action === "enable" || action === "change_phone") && (
                  <label>
                    Mobile number (9471XXXXXXX)
                    <input
                      aria-label="New mobile number"
                      type="tel"
                      autoComplete="tel"
                      inputMode="tel"
                      value={newPhone}
                      onChange={(e) => setNewPhone(e.target.value)}
                    />
                  </label>
                )}
              </div>
              <div className="credential-footer">
                <button
                  className="button primary"
                  data-testid="twofa-send-code"
                  onClick={() => void sendCode()}
                  disabled={busy}
                >
                  {busy ? <><Spinner /> Sending code…</> : <><Send size={14} /> Send code</>}
                </button>
                <button className="button ghost" onClick={reset} disabled={busy}>
                  Cancel
                </button>
              </div>
            </>
          ) : (
            <>
              <div className="form-grid">
                <label>
                  Verification code
                  <input
                    aria-label="Verification code"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    pattern="[0-9]*"
                    maxLength={6}
                    placeholder="000000"
                    value={code}
                    onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                  />
                </label>
              </div>
              <div className="credential-footer">
                <button
                  className="button primary"
                  data-testid="twofa-confirm"
                  onClick={() => void confirm()}
                  disabled={busy}
                >
                  {busy ? <><Spinner /> Confirming…</> : <><ShieldCheck size={14} /> Confirm</>}
                </button>
                <button className="button ghost" onClick={reset} disabled={busy}>
                  Cancel
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {msg && (
        <div
          className={`inline-msg ${msg.ok ? "ok" : "err"}`}
          role={msg.ok ? "status" : "alert"}
          data-testid="twofa-result"
        >
          {msg.text}
        </div>
      )}
      {guard && <ConfirmModal modal={guard} onClose={() => setGuard(null)} />}
    </div>
  );
}

function OperationsCard() {
  const [h, setH] = useState<DeepHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const load = async () => {
    setLoading(true);
    try {
      setH(await getDeepHealth());
    } catch {
      setH(null);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    void load();
    const t = setInterval(() => void load(), 10000);
    return () => clearInterval(t);
  }, []);
  const tick = h?.ingest_last_tick ? h.ingest_last_tick.slice(11, 19) + " UTC" : "—";
  return (
    <div className="panel" data-testid="operations-card">
      <div className="settings-heading">
        <span className="settings-icon">
          <Activity size={18} />
        </span>
        <div>
          <p className="kicker">RELIABILITY</p>
          <h2>Operations & health</h2>
          <p>Live service health, scheduler heartbeat and the dead-man's switch.</p>
        </div>
        <span className={`pill ${h?.status === "ok" ? "ok" : "warn"}`} data-testid="ops-status">
          {loading && !h ? <><Spinner size={12} /> Checking…</> : h?.status === "ok" ? "All healthy" : "Degraded"}
        </span>
      </div>
      {loading && !h ? (
        <LoadingState compact title="Running service health checks…" detail="Checking the database, scheduler, ingest loop, and dead-man switch." />
      ) : <div className="operations-grid">
        <span>
          <Database size={16} />
          <div>
            <small>Database</small>
            <strong>{h?.database ?? "—"}</strong>
          </div>
        </span>
        <span>
          <RadioTower size={16} />
          <div>
            <small>Scheduler</small>
            <strong>{h?.scheduler_alive ? "Alive" : "Down"}</strong>
          </div>
        </span>
        <span>
          <Wifi size={16} />
          <div>
            <small>Last candle tick</small>
            <strong>{tick}</strong>
          </div>
        </span>
        <span>
          <Activity size={16} />
          <div>
            <small>Dead-man switch</small>
            <strong>{h?.ingest_overdue ? "OVERDUE" : "Armed"}</strong>
          </div>
        </span>
      </div>}
      <button className="button secondary" data-testid="ops-refresh" onClick={() => void load()} disabled={loading}>
        {loading ? <><Spinner /> Running health check…</> : <><RefreshCw size={14} /> Run health check</>}
      </button>
    </div>
  );
}

function EnvironmentCard() {
  const [env, setEnv] = useState<string>("DEMO");
  const [botRunning, setBotRunning] = useState(false);
  const [modal, setModal] = useState<ModalSpec | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = async () => {
    setLoading(true);
    try {
      const s = await getBotStatus();
      setEnv(s.environment);
      setBotRunning(s.status !== "stopped");
    } catch {
      setMsg("Could not load the active environment.");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    void refresh();
  }, []);

  const request = (target: string) => {
    if (target === env) return;
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
        <span className={`pill ${env === "LIVE" ? "warn" : "ok"}`} data-testid="active-env">
          {loading ? <><Spinner size={12} /> Checking…</> : `${env} active`}
        </span>
      </div>
      <div className="env-options">
        <button
          className={env === "DEMO" ? "active" : ""}
          data-testid="env-demo"
          onClick={() => request("DEMO")}
          disabled={loading}
        >
          <strong>DEMO / Testnet</strong>
          <small>Fake funds · safe testing</small>
        </button>
        <button
          className={`live ${env === "LIVE" ? "active" : ""}`}
          data-testid="env-live"
          onClick={() => request("LIVE")}
          disabled={loading}
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

function StrategyLibrary() {
  const [strategies, setStrategies] = useState<StrategyInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [modal, setModal] = useState<ModalSpec | null>(null);
  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      setStrategies(await getStrategies());
    } catch {
      setStrategies([]);
      setError("Strategy releases could not be loaded. Retry to confirm the current active release.");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    void load();
  }, []);
  const selectStrategy = (strategy: StrategyInfo) =>
    setModal({
      tone: "warning",
      kicker: "VALIDATED RELEASE CHANGE",
      title: `Select ${strategy.display_name}?`,
      body: "Audit-logged; requires a stopped bot and no open position. Applies at the next reconciled start; does not start trading or change DEMO/LIVE mode.",
      details: [strategy.summary, ...strategy.caveats],
      confirmLabel: "Select release",
      onConfirm: async () => {
        await switchStrategy(strategy.name);
        await load();
        window.dispatchEvent(new Event("strategy-changed"));
      },
    });
  return (
    <div className="panel" data-testid="strategy-library">
      <div className="settings-heading">
        <span className="settings-icon">
          <Waypoints size={18} />
        </span>
        <div>
          <p className="kicker">REGISTERED PLUGINS</p>
          <h2>Strategy library</h2>
          <p>Deployed configuration is read-only; changes ship as validated releases.</p>
        </div>
      </div>
      <div className="strategy-list">
        {error && <div role="alert"><p>{error}</p><button className="button ghost" onClick={() => void load()}>Retry</button></div>}
        {loading && strategies.length === 0 && (
          <LoadingState compact title="Loading strategy releases…" detail="Reading the deployed, parity-validated plugin manifest." />
        )}
        {strategies.map((s) => (
          <article
            key={s.name}
            className={s.active ? "active" : ""}
            data-testid={`strategy-${s.name}`}
          >
            <div>
              <strong>{s.display_name}</strong>
              <code>{s.name} · release {s.validated_release}</code>
              <p>{s.summary}</p>
              <small>
                {s.symbol} · {s.interval} · {s.decision_point.replace("_", " ")}
              </small>
            </div>
            <span className="strategy-dir">{s.direction}</span>
            <details>
              <summary>How this strategy works</summary>
              <p>{s.description}</p>
              <h4>Entries</h4>
              <ul>{s.entries.map((item) => <li key={item}>{item}</li>)}</ul>
              <h4>Exits</h4>
              <ul>{s.exits.map((item) => <li key={item}>{item}</li>)}</ul>
              <h4>Risk controls</h4>
              <ul>{s.risk_controls.map((item) => <li key={item}>{item}</li>)}</ul>
              <h4>Caveats</h4>
              <ul>{s.caveats.map((item) => <li key={item}>{item}</li>)}</ul>
              <h4>Read-only release parameters</h4>
              <ul data-testid={`parameters-${s.name}`}>
                {Object.entries(s.params).map(([key, value]) => (
                  <li key={key}>{key.replaceAll("_", " ")}: <strong>{value}</strong></li>
                ))}
              </ul>
              <small>
                Warm-up {s.warmup_bars} bars · history {s.history_bars} bars ·
                validation: {s.validation_method}
              </small>
            </details>
            <div className="strategy-badges">
              {s.parity_verified && (
                <span className="pill ok" data-testid={`parity-${s.name}`}>
                  <CheckCircle2 size={12} /> Parity verified
                </span>
              )}
              <span className={`pill ${s.active ? "ok" : "warn"}`}>
                {s.active ? "Active" : "Inactive"}
              </span>
              {!s.active && (
                <button
                  className="button ghost small"
                  data-testid={`select-${s.name}`}
                  onClick={() => selectStrategy(s)}
                >
                  Select
                </button>
              )}
            </div>
          </article>
        ))}
      </div>
      {modal && <ConfirmModal modal={modal} onClose={() => setModal(null)} />}
    </div>
  );
}

function CodexCard() {
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [login, setLogin] = useState<CodexLoginStart | null>(null);
  const [loginStatus, setLoginStatus] = useState<string>("");
  const [busy, setBusy] = useState(false);

  const refresh = () =>
    getCodexStatus()
      .then((s) => setAuthed(s.authenticated))
      .catch(() => setAuthed(false));
  useEffect(() => {
    void refresh();
  }, []);

  // Poll the in-flight login until it completes.
  useEffect(() => {
    if (!login) return;
    const t = setInterval(async () => {
      try {
        const s = await getCodexLoginStatus(login.login_id);
        setLoginStatus(s.status);
        if (s.status === "completed") {
          clearInterval(t);
          setLogin(null);
          await refresh();
        } else if (s.status === "failed" || s.status === "cancelled") {
          clearInterval(t);
        }
      } catch {
        /* keep polling */
      }
    }, 2500);
    return () => clearInterval(t);
  }, [login]);

  const connect = async () => {
    setBusy(true);
    setLoginStatus("pending");
    try {
      setLogin(await startCodexLogin());
    } catch {
      setLoginStatus("failed");
    } finally {
      setBusy(false);
    }
  };

  const disconnect = async () => {
    await codexLogout();
    await refresh();
  };

  return (
    <div className="panel credential-card" data-testid="codex-card">
      <div className="settings-heading">
        <span className="settings-icon">
          <Bot size={18} />
        </span>
        <div>
          <p className="kicker">AI NEWS · CODEX SDK (GPT-5.5)</p>
          <h2>Codex authentication</h2>
          <p>Device-code login. The news agent is isolated — no exchange keys, never trades.</p>
        </div>
        <span
          className={`pill ${authed === null ? "" : authed ? "ok" : "warn"}`}
          data-testid="codex-state"
        >
          {authed === null ? "Checking…" : authed ? "Connected" : "Not connected"}
        </span>
      </div>

      {login && (
        <div className="device-code" data-testid="device-code">
          <p>1. Open this URL and 2. enter the code to authenticate:</p>
          <a href={login.verification_url} target="_blank" rel="noreferrer" className="device-url">
            {login.verification_url} <ExternalLink size={13} />
          </a>
          <div className="device-code-box">
            <code data-testid="user-code">{login.user_code}</code>
            <button
              className="icon-button"
              aria-label="Copy code"
              onClick={() => void navigator.clipboard?.writeText(login.user_code)}
            >
              <Copy size={15} />
            </button>
          </div>
          <small>Waiting for authentication… ({loginStatus})</small>
        </div>
      )}

      <div className="credential-footer">
        {!authed ? (
          <button
            className="button primary"
            data-testid="codex-connect"
            onClick={() => void connect()}
            disabled={busy || !!login}
          >
            {busy ? <><Spinner /> Starting connection…</> : <><Bot size={14} /> Connect Codex</>}
          </button>
        ) : (
          <>
            <button
              className="button secondary"
              data-testid="codex-reauth"
              onClick={() => void connect()}
              disabled={busy || !!login}
            >
              {busy ? <><Spinner /> Starting connection…</> : <><Bot size={14} /> Re-authenticate</>}
            </button>
            <button
              className="button ghost"
              data-testid="codex-logout"
              onClick={() => void disconnect()}
            >
              Disconnect
            </button>
          </>
        )}
      </div>
    </div>
  );
}

function SmsCard() {
  const [status, setStatus] = useState<SmsStatus | null>(null);
  const [statusLoading, setStatusLoading] = useState(true);
  const [userId, setUserId] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [senderId, setSenderId] = useState("NotifyDEMO");
  const [phone, setPhone] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    setStatusLoading(true);
    try {
      setStatus(await getSmsStatus());
    } catch {
      setStatus(null);
    } finally {
      setStatusLoading(false);
    }
  };
  useEffect(() => {
    void refresh();
  }, []);

  const save = async () => {
    if (!userId || !apiKey || !senderId || !phone || !currentPassword) {
      setMsg({ ok: false, text: "Fill in all fields and enter your current password." });
      return;
    }
    setBusy(true);
    try {
      await saveSmsConfig({
        user_id: userId,
        api_key: apiKey,
        sender_id: senderId,
        phone,
        current_password: currentPassword,
      });
      setMsg({ ok: true, text: "SMS credentials stored securely." });
      setApiKey("");
      setCurrentPassword("");
      await refresh();
    } catch {
      setMsg({ ok: false, text: "Could not save SMS credentials." });
    } finally {
      setBusy(false);
    }
  };

  const runTest = async () => {
    setBusy(true);
    try {
      const r = await testSms();
      setMsg({ ok: r.ok, text: r.ok ? "Test SMS sent to your phone." : `Failed: ${r.detail}` });
    } finally {
      setBusy(false);
    }
  };

  const flipEnabled = async () => {
    if (!status) return;
    setBusy(true);
    try {
      await toggleSms(!status.sms_enabled);
      await refresh();
    } catch {
      setMsg({ ok: false, text: "Could not change SMS delivery state." });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="panel credential-card" data-testid="sms-card">
      <div className="settings-heading">
        <span className="settings-icon">
          <MessageSquareText size={18} />
        </span>
        <div>
          <p className="kicker">NOTIFY.LK</p>
          <h2>SMS alerts</h2>
          <p>Fire-and-log delivery; failures retry three times and never block trading.</p>
        </div>
        <span className={`pill ${status?.configured ? "ok" : "warn"}`} data-testid="sms-state">
          {statusLoading ? <><Spinner size={12} /> Checking…</> : status === null ? "Unavailable" : status.configured ? `Configured ${status.phone_hint ?? ""}` : "Not configured"}
        </span>
      </div>
      <div className="setting-row">
        <span>
          <strong>SMS delivery</strong>
          <small>Disable only during maintenance</small>
        </span>
        <button
          className={`toggle ${status?.sms_enabled ? "on" : ""}`}
          role="switch"
          aria-checked={status?.sms_enabled ?? false}
          aria-label="Toggle SMS delivery"
          onClick={() => void flipEnabled()}
          disabled={!status || busy}
        >
          <i />
        </button>
      </div>
      <div className="form-grid">
        <label>
          User ID
          <input
            aria-label="notify.lk user ID"
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
          />
        </label>
        <label>
          API key
          <input
            type="password"
            aria-label="notify.lk API key"
            placeholder={status?.configured ? "Stored — enter to replace" : ""}
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
          />
        </label>
        <label>
          Sender ID
          <input
            aria-label="notify.lk sender ID"
            value={senderId}
            onChange={(e) => setSenderId(e.target.value)}
          />
        </label>
        <label>
          Phone (9471XXXXXXX)
          <input
            aria-label="Owner phone"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
          />
        </label>
        <label>
          Current password
          <input
            type="password"
            aria-label="notify.lk current password"
            autoComplete="current-password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
          />
        </label>
      </div>
      <div className="credential-footer">
        <button className="button primary" onClick={() => void save()} disabled={busy}>
          {busy ? <><Spinner /> Saving…</> : <><KeyRound size={14} /> Save</>}
        </button>
        <button
          className="button secondary"
          data-testid="test-sms"
          onClick={() => void runTest()}
          disabled={busy || !status?.configured}
        >
          {busy ? <><Spinner /> Working…</> : <><Send size={14} /> Send test SMS</>}
        </button>
      </div>
      {msg && (
        <div
          className={`inline-msg ${msg.ok ? "ok" : "err"}`}
          role="status"
          data-testid="sms-result"
        >
          {msg.text}
        </div>
      )}
    </div>
  );
}

function CredentialCard({ environment }: { environment: string }) {
  const [status, setStatus] = useState<CredentialStatus | null>(null);
  const [statusLoading, setStatusLoading] = useState(true);
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    setStatusLoading(true);
    try {
      setStatus(await getCredentialStatus(environment, "binance"));
    } catch {
      setStatus(null);
    } finally {
      setStatusLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [environment]);

  const save = async () => {
    if (!apiKey || !apiSecret || !currentPassword) {
      setMsg({ ok: false, text: "Enter the API key, secret, and current password." });
      return;
    }
    setBusy(true);
    try {
      await saveCredential({
        environment,
        service: "binance",
        api_key: apiKey,
        api_secret: apiSecret,
        current_password: currentPassword,
      });
      setMsg({ ok: true, text: "Credentials stored securely." });
      setApiKey("");
      setApiSecret("");
      setCurrentPassword("");
      await refresh();
    } catch {
      setMsg({ ok: false, text: "Could not save credentials." });
    } finally {
      setBusy(false);
    }
  };

  const test = async () => {
    setBusy(true);
    try {
      const result = await testBinanceConnection(environment);
      setMsg({ ok: result.ok, text: result.detail });
    } catch {
      setMsg({ ok: false, text: "Connection test failed." });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="panel credential-card" data-testid={`credential-${environment}`}>
      <div className="credential-heading">
        <div>
          <strong>{environment} · Binance USDT-M</strong>
          <small>
            {environment === "DEMO" ? "Testnet — fake funds" : "Production — real funds"}
          </small>
        </div>
        <span
          className={`pill ${status?.configured ? "ok" : "warn"}`}
          data-testid={`cred-state-${environment}`}
        >
          {statusLoading ? <><Spinner size={12} /> Checking…</> : status === null ? "Unavailable" : status.configured ? `Configured ${status.key_hint ?? ""}` : "Not configured"}
        </span>
      </div>
      <div className="form-grid">
        <label>
          API key
          <input
            type="password"
            aria-label={`${environment} API key`}
            placeholder={status?.configured ? "Stored — enter to replace" : "Enter API key"}
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
          />
        </label>
        <label>
          API secret
          <input
            type="password"
            aria-label={`${environment} API secret`}
            placeholder={status?.configured ? "Stored — enter to replace" : "Enter API secret"}
            value={apiSecret}
            onChange={(e) => setApiSecret(e.target.value)}
          />
        </label>
        <label>
          Current password
          <input
            type="password"
            aria-label={`${environment} current password`}
            autoComplete="current-password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
          />
        </label>
      </div>
      <div className="credential-footer">
        <button className="button primary" onClick={() => void save()} disabled={busy}>
          {busy ? <><Spinner /> Saving…</> : <><KeyRound size={14} /> Save credentials</>}
        </button>
        <button className="button secondary" onClick={() => void test()} disabled={busy}>
          {busy ? <><Spinner /> Testing…</> : <><PlugZap size={14} /> Test connection</>}
        </button>
      </div>
      {msg && (
        <div
          className={`inline-msg ${msg.ok ? "ok" : "err"}`}
          role="status"
          data-testid={`test-result-${environment}`}
        >
          {msg.text}
        </div>
      )}
    </div>
  );
}
