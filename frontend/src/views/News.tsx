import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Check, ExternalLink, Newspaper, RefreshCw, ShieldCheck } from "lucide-react";
import {
  getCodexStatus,
  getLatestBriefing,
  getNewsArchive,
  refreshBriefing,
  type ArchiveItem,
  type NewsBriefing,
} from "../api/client";

export function News() {
  const [briefing, setBriefing] = useState<NewsBriefing | null>(null);
  const [archive, setArchive] = useState<ArchiveItem[]>([]);
  const [codexOk, setCodexOk] = useState<boolean | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const [b, a, c] = await Promise.all([
      getLatestBriefing().catch(() => null),
      getNewsArchive().catch(() => []),
      getCodexStatus().catch(() => ({ authenticated: false })),
    ]);
    setBriefing(b);
    setArchive(a);
    setCodexOk(c.authenticated);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const refresh = async () => {
    setBusy(true);
    try {
      const r = await refreshBriefing();
      setMsg(r.detail);
      await load();
    } catch {
      setMsg("Refresh failed — is Codex connected in Settings?");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="view-stack">
      <div className="page-heading">
        <div>
          <p className="kicker">FR-10 · READ-ONLY INTELLIGENCE</p>
          <h1 data-testid="view-title">AI market briefing</h1>
          <p>Daily crypto and macro context — never a trading input.</p>
        </div>
        <button className="button secondary" data-testid="refresh-briefing" onClick={() => void refresh()} disabled={busy}>
          <RefreshCw size={15} /> Refresh briefing
        </button>
      </div>

      {codexOk === false && (
        <div className="banner warn" data-testid="codex-warning">
          <AlertTriangle size={18} /> Codex is not connected — connect it in Settings to generate
          briefings.
        </div>
      )}
      {msg && <div className="inline-msg ok" role="status">{msg}</div>}

      <div className="news-grid">
        <div className="panel briefing-panel" data-testid="briefing-panel">
          <div className="settings-heading">
            <span className="settings-icon"><Newspaper size={18} /></span>
            <div>
              <p className="kicker">
                {briefing?.generated_at
                  ? `GENERATED ${briefing.generated_at.slice(0, 16).replace("T", " ")} · ${briefing.model}`
                  : "NO BRIEFING YET"}
              </p>
              <h2>{briefing?.sentiment ? `Sentiment: ${briefing.sentiment}` : "Awaiting first briefing"}</h2>
            </div>
          </div>
          {briefing && briefing.bullets.length > 0 ? (
            <ul className="briefing-bullets">
              {briefing.bullets.map((b, i) => (
                <li key={i}>
                  <span><Check size={13} /></span>
                  <div>
                    <p>{b.text}</p>
                    {b.source && <small>{b.source}</small>}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <div className="empty-state">
              <Newspaper size={22} />
              <p>No briefing yet. Connect Codex and refresh to generate one.</p>
            </div>
          )}
          <div className="ai-boundary" data-testid="isolation-notice">
            <ShieldCheck size={18} />
            <p>{briefing?.isolation_notice}</p>
          </div>
        </div>

        <aside className="news-sidebar">
          <div className="panel">
            <p className="kicker">MACRO CALENDAR</p>
            {(briefing?.macro_calendar ?? []).map((e) => (
              <div className="calendar-event" key={e.date}>
                <time>{e.date.slice(5)}</time>
                <div>
                  <strong>{e.event}</strong>
                  <small>{e.impact} impact</small>
                </div>
              </div>
            ))}
          </div>
          <div className="panel">
            <p className="kicker">BRIEFING ARCHIVE</p>
            <div className="archive-list" data-testid="archive-list">
              {archive.length === 0 && <p className="tone-muted">No archive yet.</p>}
              {archive.map((a) => (
                <div key={a.briefing_date} className="archive-item">
                  <strong>{a.briefing_date}</strong>
                  <small>{a.sentiment}</small>
                </div>
              ))}
            </div>
          </div>
          <div className="panel sources-panel">
            <p className="kicker">SOURCES</p>
            <div className="source-tags">
              <span>CoinDesk</span>
              <span>Cointelegraph</span>
              <span>Bitcoin Magazine</span>
              <span>FOMC / CPI calendar</span>
            </div>
            <a href="https://www.coindesk.com" target="_blank" rel="noreferrer">
              CoinDesk <ExternalLink size={12} />
            </a>
          </div>
        </aside>
      </div>
    </div>
  );
}
