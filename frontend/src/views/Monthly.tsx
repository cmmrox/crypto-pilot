import { useCallback, useEffect, useState } from "react";
import { ShieldCheck, Wallet } from "lucide-react";
import { getMonthly, markWithdrawn, type MonthRow } from "../api/client";
import { ConfirmModal, type ModalSpec } from "../components/ConfirmModal";

function m(v: string): string {
  return Number(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function Monthly() {
  const [rows, setRows] = useState<MonthRow[]>([]);
  const [modal, setModal] = useState<ModalSpec | null>(null);

  const load = useCallback(async () => {
    try {
      setRows(await getMonthly());
    } catch {
      setRows([]);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="view-stack">
      <div className="page-heading">
        <div>
          <p className="kicker">FR-08 · WITHDRAWAL DISCIPLINE</p>
          <h1 data-testid="view-title">Monthly ledger</h1>
          <p>Realized performance, independent breakers and the manual withdrawal allowance.</p>
        </div>
      </div>

      <div className="panel">
        <div className="table-scroll">
          <table className="ledger-table" data-testid="monthly-table">
            <thead>
              <tr>
                <th>Month</th>
                <th>Trades</th>
                <th>Realized</th>
                <th>Fees</th>
                <th>Net</th>
                <th>Withdrawn</th>
                <th>Withdrawable</th>
                <th>Breakers</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && (
                <tr>
                  <td colSpan={9} className="empty-cell">
                    No closed trades yet.
                  </td>
                </tr>
              )}
              {rows.map((r) => (
                <tr key={r.month} data-testid={`month-${r.month}`}>
                  <td><strong>{r.month}</strong></td>
                  <td>{r.trades}</td>
                  <td className={Number(r.realized_pnl) >= 0 ? "tone-ok" : "tone-err"}>${m(r.realized_pnl)}</td>
                  <td>−${m(r.fees)}</td>
                  <td className={Number(r.net) >= 0 ? "tone-ok" : "tone-err"}>${m(r.net)}</td>
                  <td>{Number(r.withdrawn) > 0 ? `$${m(r.withdrawn)}` : "—"}</td>
                  <td className="tone-ok">${m(r.withdrawable)}</td>
                  <td>
                    <span className="pill ok">L {r.long_breaker}</span>{" "}
                    <span className="pill ok">S {r.short_breaker}</span>
                  </td>
                  <td>
                    {Number(r.withdrawable) > 0 && (
                      <button
                        className="button ghost small"
                        data-testid={`mark-${r.month}`}
                        onClick={() =>
                          setModal({
                            tone: "warning",
                            kicker: "MANUAL BOOKKEEPING",
                            title: `Mark $${m(r.withdrawable)} as withdrawn for ${r.month}?`,
                            body: "This records an owner action in the ledger. CryptoPilot never moves funds or calls a withdrawal API.",
                            confirmLabel: "Mark withdrawn",
                            onConfirm: async () => {
                              await markWithdrawn(r.month);
                              await load();
                            },
                          })
                        }
                      >
                        <Wallet size={13} /> Mark withdrawn
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="panel withdrawal-rule">
        <ShieldCheck size={22} />
        <div>
          <p className="kicker">WITHDRAWAL RULE</p>
          <h2>Manual bookkeeping only</h2>
          <p>
            Withdrawable = max(0, realized net profit) × 10%. CryptoPilot never moves funds and
            the Binance API key never has withdrawal permission.
          </p>
        </div>
      </div>

      {modal && <ConfirmModal modal={modal} onClose={() => setModal(null)} />}
    </div>
  );
}
