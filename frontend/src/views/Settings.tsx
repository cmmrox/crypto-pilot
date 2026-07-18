import { useEffect, useState } from "react";
import {
  Bot,
  CheckCircle2,
  Copy,
  ExternalLink,
  KeyRound,
  MessageSquareText,
  PlugZap,
  Send,
  ShieldCheck,
  Waypoints,
} from "lucide-react";
import {
  codexLogout,
  getCodexLoginStatus,
  getCodexStatus,
  getCredentialStatus,
  getSmsStatus,
  getStrategies,
  saveCredential,
  saveSmsConfig,
  startCodexLogin,
  testBinanceConnection,
  testSms,
  toggleSms,
  type CodexLoginStart,
  type CredentialStatus,
  type SmsStatus,
  type StrategyInfo,
} from "../api/client";

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
      <StrategyLibrary />
      <CodexCard />
      <CredentialCard environment="DEMO" />
      <CredentialCard environment="LIVE" />
      <SmsCard />
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

function StrategyLibrary() {
  const [strategies, setStrategies] = useState<StrategyInfo[]>([]);
  useEffect(() => {
    void getStrategies().then(setStrategies).catch(() => setStrategies([]));
  }, []);
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
        {strategies.map((s) => (
          <article key={s.name} className={s.active ? "active" : ""} data-testid={`strategy-${s.name}`}>
            <div>
              <strong>{s.name}</strong>
              <code>release {s.validated_release}</code>
            </div>
            <span className="strategy-dir">{s.direction}</span>
            <div className="strategy-badges">
              {s.parity_verified && (
                <span className="pill ok" data-testid={`parity-${s.name}`}>
                  <CheckCircle2 size={12} /> Parity verified
                </span>
              )}
              <span className={`pill ${s.active ? "ok" : "warn"}`}>
                {s.active ? "Active" : "Inactive"}
              </span>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}

function CodexCard() {
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [login, setLogin] = useState<CodexLoginStart | null>(null);
  const [loginStatus, setLoginStatus] = useState<string>("");
  const [busy, setBusy] = useState(false);

  const refresh = () => getCodexStatus().then((s) => setAuthed(s.authenticated)).catch(() => setAuthed(false));
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
        <span className="settings-icon"><Bot size={18} /></span>
        <div>
          <p className="kicker">AI NEWS · CODEX SDK (GPT-5.5)</p>
          <h2>Codex authentication</h2>
          <p>Device-code login. The news agent is isolated — no exchange keys, never trades.</p>
        </div>
        <span className={`pill ${authed ? "ok" : "warn"}`} data-testid="codex-state">
          {authed ? "Connected" : "Not connected"}
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
          <button className="button primary" data-testid="codex-connect" onClick={() => void connect()} disabled={busy || !!login}>
            <Bot size={14} /> Connect Codex
          </button>
        ) : (
          <>
            <button className="button secondary" data-testid="codex-reauth" onClick={() => void connect()} disabled={busy || !!login}>
              <Bot size={14} /> Re-authenticate
            </button>
            <button className="button ghost" data-testid="codex-logout" onClick={() => void disconnect()}>
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
  const [userId, setUserId] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [senderId, setSenderId] = useState("NotifyDEMO");
  const [phone, setPhone] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = () => getSmsStatus().then(setStatus).catch(() => setStatus(null));
  useEffect(() => {
    void refresh();
  }, []);

  const save = async () => {
    if (!userId || !apiKey || !senderId || !phone) {
      setMsg({ ok: false, text: "Fill in all notify.lk fields." });
      return;
    }
    setBusy(true);
    try {
      await saveSmsConfig({ user_id: userId, api_key: apiKey, sender_id: senderId, phone });
      setMsg({ ok: true, text: "SMS credentials stored securely." });
      setApiKey("");
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
    await toggleSms(!status.sms_enabled);
    await refresh();
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
          {status?.configured ? `Configured ${status.phone_hint ?? ""}` : "Not configured"}
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
        >
          <i />
        </button>
      </div>
      <div className="form-grid">
        <label>
          User ID
          <input aria-label="notify.lk user ID" value={userId} onChange={(e) => setUserId(e.target.value)} />
        </label>
        <label>
          API key
          <input type="password" aria-label="notify.lk API key" placeholder={status?.configured ? "Stored — enter to replace" : ""} value={apiKey} onChange={(e) => setApiKey(e.target.value)} />
        </label>
        <label>
          Sender ID
          <input aria-label="notify.lk sender ID" value={senderId} onChange={(e) => setSenderId(e.target.value)} />
        </label>
        <label>
          Phone (9471XXXXXXX)
          <input aria-label="Owner phone" value={phone} onChange={(e) => setPhone(e.target.value)} />
        </label>
      </div>
      <div className="credential-footer">
        <button className="button primary" onClick={() => void save()} disabled={busy}>
          <KeyRound size={14} /> Save
        </button>
        <button className="button secondary" data-testid="test-sms" onClick={() => void runTest()} disabled={busy || !status?.configured}>
          <Send size={14} /> Send test SMS
        </button>
      </div>
      {msg && (
        <div className={`inline-msg ${msg.ok ? "ok" : "err"}`} role="status" data-testid="sms-result">
          {msg.text}
        </div>
      )}
    </div>
  );
}

function CredentialCard({ environment }: { environment: string }) {
  const [status, setStatus] = useState<CredentialStatus | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = () =>
    getCredentialStatus(environment, "binance")
      .then(setStatus)
      .catch(() => setStatus(null));

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [environment]);

  const save = async () => {
    if (!apiKey || !apiSecret) {
      setMsg({ ok: false, text: "Enter both the API key and secret." });
      return;
    }
    setBusy(true);
    try {
      await saveCredential({ environment, service: "binance", api_key: apiKey, api_secret: apiSecret });
      setMsg({ ok: true, text: "Credentials stored securely." });
      setApiKey("");
      setApiSecret("");
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
        <span className={`pill ${status?.configured ? "ok" : "warn"}`} data-testid={`cred-state-${environment}`}>
          {status?.configured ? `Configured ${status.key_hint ?? ""}` : "Not configured"}
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
      </div>
      <div className="credential-footer">
        <button className="button primary" onClick={() => void save()} disabled={busy}>
          <KeyRound size={14} /> Save credentials
        </button>
        <button className="button secondary" onClick={() => void test()} disabled={busy}>
          <PlugZap size={14} /> Test connection
        </button>
      </div>
      {msg && (
        <div className={`inline-msg ${msg.ok ? "ok" : "err"}`} role="status" data-testid={`test-result-${environment}`}>
          {msg.text}
        </div>
      )}
    </div>
  );
}
