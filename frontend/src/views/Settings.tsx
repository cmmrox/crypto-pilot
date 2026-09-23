import { CheckCircle2, ShieldCheck } from "lucide-react";
import { SecurityCard } from "../features/settings/SecurityCard";
import { OperationsCard } from "../features/settings/OperationsCard";
import { EnvironmentCard } from "../features/settings/EnvironmentCard";
import { StrategyLibrary } from "../features/settings/StrategyLibrary";
import { CodexCard } from "../features/settings/CodexCard";
import { SmsCard } from "../features/settings/SmsCard";
import { CredentialCard } from "../features/settings/CredentialCard";

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
      <SecurityCard />
      <EnvironmentCard />
      <StrategyLibrary />
      <CodexCard />
      <CredentialCard environment="DEMO" />
      <CredentialCard environment="LIVE" />
      <SmsCard />
      <OperationsCard />
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
