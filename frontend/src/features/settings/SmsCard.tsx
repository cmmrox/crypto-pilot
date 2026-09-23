import { useEffect, useState } from "react";
import { KeyRound, MessageSquareText, Send } from "lucide-react";
import { getSmsStatus, saveSmsConfig, testSms, toggleSms, type SmsStatus } from "../../api/client";
import { Spinner } from "../../components/AsyncState";

export function SmsCard() {
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
          {statusLoading ? (
            <>
              <Spinner size={12} /> Checking…
            </>
          ) : status === null ? (
            "Unavailable"
          ) : status.configured ? (
            `Configured ${status.phone_hint ?? ""}`
          ) : (
            "Not configured"
          )}
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
          {busy ? (
            <>
              <Spinner /> Saving…
            </>
          ) : (
            <>
              <KeyRound size={14} /> Save
            </>
          )}
        </button>
        <button
          className="button secondary"
          data-testid="test-sms"
          onClick={() => void runTest()}
          disabled={busy || !status?.configured}
        >
          {busy ? (
            <>
              <Spinner /> Working…
            </>
          ) : (
            <>
              <Send size={14} /> Send test SMS
            </>
          )}
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
