import { useEffect, useState } from "react";
import { BrowserRouter } from "react-router-dom";
import { Login } from "./auth/Login";
import { Otp } from "./auth/Otp";
import { Shell } from "./shell/Shell";
import { useAuth } from "./auth/store";

interface OtpFlow {
  token: string;
  phoneHint: string | null;
}

/**
 * Root component. Routes between the auth flow (Login → SMS OTP) and the
 * authenticated Shell based on the auth store. The Shell is only mounted
 * for authenticated sessions — mounting itself is the route guard.
 */
export function App() {
  const status = useAuth((s) => s.status);
  const bootstrap = useAuth((s) => s.bootstrap);
  const [otpFlow, setOtpFlow] = useState<OtpFlow | null>(null);

  useEffect(() => {
    void bootstrap();
  }, [bootstrap]);

  // Clear the in-flight OTP challenge once authenticated so a later sign-out
  // returns to the Login screen, not a stale OTP prompt.
  useEffect(() => {
    if (status === "authenticated" && otpFlow !== null) {
      setOtpFlow(null);
    }
  }, [status, otpFlow]);

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
    if (otpFlow) {
      return (
        <Otp
          otpToken={otpFlow.token}
          phoneHint={otpFlow.phoneHint}
          onBack={() => setOtpFlow(null)}
        />
      );
    }
    return <Login onOtpRequired={(token, phoneHint) => setOtpFlow({ token, phoneHint })} />;
  }

  return (
    <BrowserRouter>
      <Shell />
    </BrowserRouter>
  );
}
