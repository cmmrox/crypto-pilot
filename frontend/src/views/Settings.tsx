import { useEffect, useState } from "react";
import { CheckCircle2, KeyRound, PlugZap, ShieldCheck, Waypoints } from "lucide-react";
import {
  getCredentialStatus,
  getStrategies,
  saveCredential,
  testBinanceConnection,
  type CredentialStatus,
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
      <CredentialCard environment="DEMO" />
      <CredentialCard environment="LIVE" />
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
