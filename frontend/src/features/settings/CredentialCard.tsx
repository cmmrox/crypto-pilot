import { useEffect, useState } from "react";
import { KeyRound, PlugZap } from "lucide-react";
import {
  getCredentialStatus,
  saveCredential,
  testBinanceConnection,
  type CredentialStatus,
} from "../../api/client";
import { Spinner } from "../../components/AsyncState";

export function CredentialCard({ environment }: { environment: string }) {
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
          {statusLoading ? (
            <>
              <Spinner size={12} /> Checking…
            </>
          ) : status === null ? (
            "Unavailable"
          ) : status.configured ? (
            `Configured ${status.key_hint ?? ""}`
          ) : (
            "Not configured"
          )}
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
          {busy ? (
            <>
              <Spinner /> Saving…
            </>
          ) : (
            <>
              <KeyRound size={14} /> Save credentials
            </>
          )}
        </button>
        <button className="button secondary" onClick={() => void test()} disabled={busy}>
          {busy ? (
            <>
              <Spinner /> Testing…
            </>
          ) : (
            <>
              <PlugZap size={14} /> Test connection
            </>
          )}
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
