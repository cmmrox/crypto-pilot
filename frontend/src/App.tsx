import { useEffect, useState } from "react";
import { BrowserRouter } from "react-router-dom";
import { Login } from "./auth/Login";
import { Totp } from "./auth/Totp";
import { Shell } from "./shell/Shell";
import { useAuth } from "./auth/store";

/**
 * Root component. Routes between the auth flow (Login → TOTP) and the
 * authenticated Shell based on the auth store. The Shell is only mounted
 * for authenticated sessions — mounting itself is the route guard.
 */
export function App() {
  const status = useAuth((s) => s.status);
  const bootstrap = useAuth((s) => s.bootstrap);
  const [totpToken, setTotpToken] = useState<string | null>(null);

  useEffect(() => {
    void bootstrap();
  }, [bootstrap]);

  // Clear the in-flight TOTP token once authenticated so a later sign-out
  // returns to the Login screen, not a stale TOTP prompt.
  useEffect(() => {
    if (status === "authenticated" && totpToken !== null) {
      setTotpToken(null);
    }
  }, [status, totpToken]);

  if (status === "loading") {
    return (
      <main className="splash" data-testid="splash">
        <div className="brand-lockup brand-lockup-large">
          <span className="brand-icon" />
          <strong>CryptoPilot</strong>
        </div>
        <p>Loading…</p>
      </main>
    );
  }

  if (status === "unauthenticated") {
    if (totpToken) {
      return <Totp totpToken={totpToken} onBack={() => setTotpToken(null)} />;
    }
    return <Login onPasswordVerified={setTotpToken} />;
  }

  return (
    <BrowserRouter>
      <Shell />
    </BrowserRouter>
  );
}
