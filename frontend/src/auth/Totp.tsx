import { useState } from "react";
import { AlertTriangle, ArrowLeft, ShieldCheck, Smartphone } from "lucide-react";
import { getMe, setTokens, verifyTotp } from "../api/client";
import { useAuth } from "./store";

/** Second factor: verify the 6-digit authenticator code to complete sign-in. */
export function Totp({ totpToken, onBack }: { totpToken: string; onBack: () => void }) {
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const setAuthenticated = useAuth((s) => s.setAuthenticated);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (code.length !== 6) {
      setError("Enter the 6-digit code from your authenticator app.");
      return;
    }
    setError("");
    setBusy(true);
    try {
      const tokens = await verifyTotp(totpToken, code);
      setTokens(tokens);
      const user = await getMe();
      setAuthenticated(user);
    } catch {
      setError("That authenticator code is invalid or expired.");
      setBusy(false);
    }
  };

  return (
    <main className="totp-shell">
      <form className="totp-card" onSubmit={submit}>
        <button type="button" className="icon-button totp-back" aria-label="Back to password" onClick={onBack}>
          <ArrowLeft size={17} />
        </button>
        <span className="totp-icon">
          <Smartphone size={24} />
        </span>
        <p className="kicker">TWO-STEP VERIFICATION</p>
        <h1>Enter your 6-digit code</h1>
        <p>Open your authenticator app and enter the current code for CryptoPilot.</p>
        <label className="sr-only" htmlFor="totp">
          Authentication code
        </label>
        <input
          id="totp"
          className="totp-input"
          aria-label="Authentication code"
          inputMode="numeric"
          maxLength={6}
          placeholder="000000"
          value={code}
          onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
          autoFocus
        />
        {error && (
          <div className="form-error" role="alert">
            <AlertTriangle size={16} />
            {error}
          </div>
        )}
        <button className="button primary full" type="submit" disabled={busy}>
          {busy ? "Verifying…" : "Verify & enter"}
        </button>
        <div className="totp-required">
          <ShieldCheck size={15} />
          Two-factor verification is mandatory for every sign-in.
        </div>
      </form>
    </main>
  );
}
