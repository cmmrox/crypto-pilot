import { useEffect, useState } from "react";
import { Bot, Copy, ExternalLink } from "lucide-react";
import {
  codexLogout,
  getCodexLoginStatus,
  getCodexStatus,
  startCodexLogin,
  type CodexLoginStart,
} from "../../api/client";
import { Spinner } from "../../components/AsyncState";

export function CodexCard() {
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [login, setLogin] = useState<CodexLoginStart | null>(null);
  const [loginStatus, setLoginStatus] = useState<string>("");
  const [busy, setBusy] = useState(false);

  const refresh = () =>
    getCodexStatus()
      .then((s) => setAuthed(s.authenticated))
      .catch(() => setAuthed(false));
  useEffect(() => {
    void refresh();
  }, []);

  // Poll the in-flight login until it completes.
  useEffect(() => {
    if (!login) return;
    const t = setInterval(async () => {
      try {
        const s = await getCodexLoginStatus(login.login_id);
        setLoginStatus(s.status);
        if (s.status === "completed") {
          clearInterval(t);
          setLogin(null);
          await refresh();
        } else if (s.status === "failed" || s.status === "cancelled") {
          clearInterval(t);
        }
      } catch {
        /* keep polling */
      }
    }, 2500);
    return () => clearInterval(t);
  }, [login]);

  const connect = async () => {
    setBusy(true);
    setLoginStatus("pending");
    try {
      setLogin(await startCodexLogin());
    } catch {
      setLoginStatus("failed");
    } finally {
      setBusy(false);
    }
  };

  const disconnect = async () => {
    await codexLogout();
    await refresh();
  };

  return (
    <div className="panel credential-card" data-testid="codex-card">
      <div className="settings-heading">
        <span className="settings-icon">
          <Bot size={18} />
        </span>
        <div>
          <p className="kicker">AI NEWS · CODEX SDK (GPT-5.5)</p>
          <h2>Codex authentication</h2>
          <p>Device-code login. The news agent is isolated — no exchange keys, never trades.</p>
        </div>
        <span
          className={`pill ${authed === null ? "" : authed ? "ok" : "warn"}`}
          data-testid="codex-state"
        >
          {authed === null ? "Checking…" : authed ? "Connected" : "Not connected"}
        </span>
      </div>

      {login && (
        <div className="device-code" data-testid="device-code">
          <p>1. Open this URL and 2. enter the code to authenticate:</p>
          <a href={login.verification_url} target="_blank" rel="noreferrer" className="device-url">
            {login.verification_url} <ExternalLink size={13} />
          </a>
          <div className="device-code-box">
            <code data-testid="user-code">{login.user_code}</code>
            <button
              className="icon-button"
              aria-label="Copy code"
              onClick={() => void navigator.clipboard?.writeText(login.user_code)}
            >
              <Copy size={15} />
            </button>
          </div>
          <small>Waiting for authentication… ({loginStatus})</small>
        </div>
      )}

      <div className="credential-footer">
        {!authed ? (
          <button
            className="button primary"
            data-testid="codex-connect"
            onClick={() => void connect()}
            disabled={busy || !!login}
          >
            {busy ? (
              <>
                <Spinner /> Starting connection…
              </>
            ) : (
              <>
                <Bot size={14} /> Connect Codex
              </>
            )}
          </button>
        ) : (
          <>
            <button
              className="button secondary"
              data-testid="codex-reauth"
              onClick={() => void connect()}
              disabled={busy || !!login}
            >
              {busy ? (
                <>
                  <Spinner /> Starting connection…
                </>
              ) : (
                <>
                  <Bot size={14} /> Re-authenticate
                </>
              )}
            </button>
            <button
              className="button ghost"
              data-testid="codex-logout"
              onClick={() => void disconnect()}
            >
              Disconnect
            </button>
          </>
        )}
      </div>
    </div>
  );
}
