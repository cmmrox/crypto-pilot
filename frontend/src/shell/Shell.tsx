import { useState } from "react";
import { NavLink, Route, Routes, Navigate } from "react-router-dom";
import {
  Bitcoin,
  CalendarDays,
  LayoutDashboard,
  ListTree,
  LogOut,
  Menu,
  Newspaper,
  Settings,
  ShieldCheck,
  TrendingUp,
  X,
} from "lucide-react";
import { useAuth } from "../auth/store";
import { PlaceholderView } from "./PlaceholderView";
import { Events } from "../views/Events";
import { Overview } from "../views/Overview";
import { Settings as SettingsView } from "../views/Settings";

const NAV = [
  { to: "/overview", label: "Overview", icon: LayoutDashboard, stage: "Stage 5" },
  { to: "/trades", label: "Trades", icon: TrendingUp, stage: "Stage 6" },
  { to: "/monthly", label: "Monthly", icon: CalendarDays, stage: "Stage 6" },
  { to: "/news", label: "News briefing", icon: Newspaper, stage: "Stage 8" },
  { to: "/events", label: "Event ledger", icon: ListTree, stage: "Stage 2" },
  { to: "/settings", label: "Settings", icon: Settings, stage: "Stage 9" },
];

export function Shell() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const user = useAuth((s) => s.user);
  const signOut = useAuth((s) => s.signOut);

  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileOpen ? "open" : ""}`} aria-label="Primary navigation">
        <div className="sidebar-brand">
          <div className="brand-lockup">
            <span className="brand-icon">
              <Bitcoin size={22} />
            </span>
            <span>
              <strong>CryptoPilot</strong>
              <small>Trading control room</small>
            </span>
          </div>
          <button
            className="icon-button sidebar-close"
            aria-label="Close navigation"
            onClick={() => setMobileOpen(false)}
          >
            <X size={18} />
          </button>
        </div>
        <nav>
          {NAV.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) => (isActive ? "active" : "")}
                onClick={() => setMobileOpen(false)}
              >
                <Icon size={18} />
                <span>{item.label}</span>
              </NavLink>
            );
          })}
        </nav>
        <div className="sidebar-status">
          <div className="strategy-card-mini">
            <p className="kicker">ACTIVE STRATEGY</p>
            <strong>Trend Rider v6</strong>
            <small>BTCUSDT · 4h · LONG + SHORT</small>
            <span>
              <ShieldCheck size={13} />
              Validated release 6.0
            </span>
          </div>
          <button className="sign-out-button" onClick={() => void signOut()}>
            <LogOut size={16} />
            Sign out
          </button>
        </div>
      </aside>
      {mobileOpen && (
        <button
          className="sidebar-scrim"
          aria-label="Close navigation overlay"
          onClick={() => setMobileOpen(false)}
        />
      )}

      <div className="main-shell">
        <header className="topbar">
          <button
            className="icon-button mobile-menu"
            aria-label="Open navigation"
            onClick={() => setMobileOpen(true)}
          >
            <Menu size={19} />
          </button>
          <div className="environment-badge" data-testid="environment-badge">
            <strong>DEMO</strong>
            <span>Testnet funds</span>
          </div>
          <div className="topbar-actions">
            <div className="profile-chip" data-testid="owner-email">
              <span>CP</span>
              <div>
                <strong>{user?.email ?? "Owner"}</strong>
                <small>Owner role</small>
              </div>
            </div>
          </div>
        </header>
        <main className="content">
          <Routes>
            <Route path="/" element={<Navigate to="/overview" replace />} />
            <Route path="/overview" element={<Overview />} />
            <Route path="/events" element={<Events />} />
            <Route path="/settings" element={<SettingsView />} />
            {NAV.filter(
              (i) => !["/overview", "/events", "/settings"].includes(i.to),
            ).map((item) => (
              <Route
                key={item.to}
                path={item.to}
                element={<PlaceholderView title={item.label} stage={item.stage} />}
              />
            ))}
            <Route path="*" element={<Navigate to="/overview" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
