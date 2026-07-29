import { useEffect, useState } from "react";
import { AlertTriangle, ArrowLeft, MessageSquareText, ShieldCheck } from "lucide-react";
import { ApiError, clearTokens, getMe, resendOtp, setTokens, verifyOtp } from "../api/client";
import { useAuth } from "./store";
import { Spinner } from "../components/AsyncState";

const RESEND_SECONDS = 60;

/** Second factor: verify the 6-digit SMS code to complete sign-in. */
export function Otp({
  otpToken,
  phoneHint,
  onBack,
}: {
  otpToken: string;
  phoneHint: string | null;
  onBack: () => void;
}) {
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [resendBusy, setResendBusy] = useState(false);
  // The resend cooldown is derived from an absolute deadline versus the wall
  // clock rather than a decremented counter. A single re-render after any time
  // jump then reports the correct remaining seconds — robust against React
  // batching, background-tab timer throttling, and fake clocks under test.
  const [deadline, setDeadline] = useState(() => Date.now() + RESEND_SECONDS * 1000);
  const [now, setNow] = useState(() => Date.now());
  const cooldown = Math.max(0, Math.ceil((deadline - now) / 1000));
  const setAuthenticated = useAuth((s) => s.setAuthenticated);

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (code.length !== 6) {
      setError("Enter the 6-digit code from the SMS.");
      return;
    }
    setError("");
    setNotice("");
    setBusy(true);
    let tokensIssued = false;
    try {
      const tokens = await verifyOtp(otpToken, code);
      setTokens(tokens);
      tokensIssued = true;
      setAuthenticated(await getMe());
    } catch (err) {
      if (tokensIssued) {
        clearTokens();
        setError(
          "The code was accepted, but the new session could not be verified. Sign in again.",
        );
      } else if (err instanceof ApiError && err.status === 429) {
        setError("Too many attempts. Your account is temporarily locked — sign in again later.");
      } else if (err instanceof ApiError && /expired|used|not found/i.test(err.message)) {
        setError("That code has expired. Go back and sign in again for a new code.");
      } else if (err instanceof ApiError && /too many/i.test(err.message)) {
        setError("Too many incorrect attempts. Go back and sign in again.");
      } else {
        setError("That code is incorrect. Check the SMS and try again.");
      }
      setBusy(false);
    }
  };

  const startCooldown = () => {
    const t = Date.now();
    setNow(t);
    setDeadline(t + RESEND_SECONDS * 1000);
  };

  const resend = async () => {
    if (cooldown > 0 || resendBusy) return;
    setError("");
    setNotice("");
    setResendBusy(true);
    try {
      await resendOtp(otpToken);
      setNotice("A new code has been sent.");
      startCooldown();
    } catch (err) {
      if (err instanceof ApiError && err.status === 429) {
        if (/too many verification codes|try again later/i.test(err.message)) {
          setError("Too many verification codes have been requested. Try again later.");
        } else {
          setError("Please wait before requesting another code.");
          startCooldown();
        }
      } else {
        setError("Could not send a new code. Go back and sign in again.");
      }
    } finally {
      setResendBusy(false);
    }
  };

  return (
    <main className="otp-shell">
      <form className="otp-card" onSubmit={submit}>
        <button
          type="button"
          className="icon-button otp-back"
          aria-label="Back to password"
          onClick={onBack}
        >
          <ArrowLeft size={17} />
        </button>
        <span className="otp-icon">
          <MessageSquareText size={24} />
        </span>
        <p className="kicker">TWO-STEP VERIFICATION</p>
        <h1>Enter your 6-digit code</h1>
        <p>
          We sent a verification code by SMS{phoneHint ? ` to ${phoneHint}` : ""}. Enter it below to
          finish signing in.
        </p>
        <label className="sr-only" htmlFor="otp">
          Authentication code
        </label>
        <input
          id="otp"
          className="otp-input"
          aria-label="Authentication code"
          inputMode="numeric"
          autoComplete="one-time-code"
          pattern="[0-9]*"
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
        {notice && (
          <div className="inline-msg ok" role="status">
            {notice}
          </div>
        )}
        <button className="button primary full" type="submit" disabled={busy}>
          {busy ? <><Spinner /> Verifying code…</> : "Verify & enter"}
        </button>
        <button
          type="button"
          className="button ghost full"
          data-testid="resend-otp"
          onClick={() => void resend()}
          disabled={cooldown > 0 || resendBusy}
        >
          {resendBusy ? <><Spinner /> Sending code…</> : cooldown > 0 ? `Resend code in ${cooldown}s` : "Resend code"}
        </button>
        <div className="otp-required">
          <ShieldCheck size={15} />
          Two-factor verification protects every sign-in.
        </div>
      </form>
    </main>
  );
}
