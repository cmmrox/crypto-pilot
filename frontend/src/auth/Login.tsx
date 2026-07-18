import { useState } from "react";
import { AlertTriangle, ArrowRight, Bitcoin, Eye, EyeOff, ShieldCheck } from "lucide-react";
import { ApiError, login } from "../api/client";

/** Owner login (email + password). On success, advances to TOTP verification. */
export function Login({ onPasswordVerified }: { onPasswordVerified: (totpToken: string) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim()) || password.length < 1) {
      setError("Enter a valid email address and your password.");
      return;
    }
    setError("");
    setBusy(true);
    try {
      const { totp_token } = await login(email.trim(), password);
      onPasswordVerified(totp_token);
    } catch (err) {
      if (err instanceof ApiError && err.status === 429) {
        setError("Too many attempts. Your account is temporarily locked — try again later.");
      } else {
        setError("Invalid email or password.");
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="auth-shell">
      <section className="auth-story">
        <div className="brand-lockup brand-lockup-large">
          <span className="brand-icon">
            <Bitcoin size={27} />
          </span>
          <span>
            <strong>CryptoPilot</strong>
            <small>Trading control room</small>
          </span>
        </div>
        <div className="auth-copy">
          <p className="kicker">OWNER CONSOLE · PROTECTED ACCESS</p>
          <h1>
            Every signal.
            <br />
            Every safeguard.
            <br />
            <em>One clear control room.</em>
          </h1>
          <p>
            Operate Trend Rider v6 with closed-candle discipline, exchange reconciliation,
            independent loss breakers and a complete audit trail.
          </p>
        </div>
      </section>
      <section className="auth-form-wrap">
        <form className="auth-card" onSubmit={submit} noValidate>
          <p className="kicker">SINGLE-OWNER WORKSPACE</p>
          <h2>Sign in securely</h2>
          <p>Use your owner credentials. Authenticator verification always follows.</p>
          <label>
            Email
            <input
              aria-label="Email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>
          <label>
            Password
            <span className="password-field">
              <input
                aria-label="Password"
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <button
                type="button"
                className="icon-button"
                aria-label={showPassword ? "Hide password" : "Show password"}
                onClick={() => setShowPassword((v) => !v)}
              >
                {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
              </button>
            </span>
          </label>
          {error && (
            <div className="form-error" role="alert">
              <AlertTriangle size={16} />
              {error}
            </div>
          )}
          <button className="button primary full" type="submit" disabled={busy}>
            {busy ? "Verifying…" : "Continue"} <ArrowRight size={16} />
          </button>
          <div className="auth-security-note">
            <ShieldCheck size={16} />
            <span>JWT session · Argon2 password hash · mandatory TOTP · TLS-only production access</span>
          </div>
        </form>
      </section>
    </main>
  );
}
