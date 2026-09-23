import { useEffect, useState } from "react";
import { Lock, Send, ShieldCheck, Smartphone } from "lucide-react";
import {
  ApiError,
  confirmSecurityChange,
  getSecurityStatus,
  startSecurityChange,
  type SecurityAction,
  type SecurityStatus,
} from "../../api/client";
import { ConfirmModal, type ModalSpec } from "../../components/ConfirmModal";
import { Spinner } from "../../components/AsyncState";

export function SecurityCard() {
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
          {statusLoading ? (
            <>
              <Spinner size={12} /> Checking…
            </>
          ) : status === null ? (
            "Unavailable"
          ) : enabled ? (
            `On ${status.phone_hint ?? ""}`
          ) : (
            "Off"
          )}
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
                  {busy ? (
                    <>
                      <Spinner /> Sending code…
                    </>
                  ) : (
                    <>
                      <Send size={14} /> Send code
                    </>
                  )}
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
                  {busy ? (
                    <>
                      <Spinner /> Confirming…
                    </>
                  ) : (
                    <>
                      <ShieldCheck size={14} /> Confirm
                    </>
                  )}
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
