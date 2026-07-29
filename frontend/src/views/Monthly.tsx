import { useCallback, useEffect, useState } from "react";
import { ShieldCheck, Wallet } from "lucide-react";
import { getMonthly, markWithdrawn, type MonthRow } from "../api/client";
import { ConfirmModal, type ModalSpec } from "../components/ConfirmModal";
import { LoadingState } from "../components/AsyncState";
import { formatUsd, isNegativeDecimal, isPositiveDecimal } from "../utils/decimal";

export function Monthly() {
  const [rows, setRows] = useState<MonthRow[]>([]);
  const [modal, setModal] = useState<ModalSpec | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setRows(await getMonthly());
    } catch {
      setRows([]);
      setError("Could not load the monthly ledger. Check the connection and try again.");
    } finally {
      setLoading(false);
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

      {error && (
        <div className="form-error" role="alert">
          {error}
        </div>
      )}

      <div className="panel" aria-busy={loading}>
        {loading && rows.length === 0 ? (
          <LoadingState
            title="Loading monthly ledger…"
            detail="Calculating confirmed realized results and withdrawal allowances."
          />
        ) : (
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
                {!loading && rows.length === 0 && !error && (
                  <tr>
                    <td colSpan={9} className="empty-cell">
                      No closed trades yet.
                    </td>
                  </tr>
                )}
                {rows.map((r) => (
                  <tr key={r.month} data-testid={`month-${r.month}`}>
                    <td>
                      <strong>{r.month}</strong>
                    </td>
                    <td>{r.trades}</td>
                    <td className={isNegativeDecimal(r.realized_pnl) ? "tone-err" : "tone-ok"}>
                      {formatUsd(r.realized_pnl)}
                    </td>
                    <td>−{formatUsd(r.fees)}</td>
                    <td className={isNegativeDecimal(r.net) ? "tone-err" : "tone-ok"}>
                      {formatUsd(r.net)}
                    </td>
                    <td>{isPositiveDecimal(r.withdrawn) ? formatUsd(r.withdrawn) : "—"}</td>
                    <td className="tone-ok">{formatUsd(r.withdrawable)}</td>
                    <td>
                      <span className="pill ok">L {r.long_breaker}</span>{" "}
                      <span className="pill ok">S {r.short_breaker}</span>
                    </td>
                    <td>
                      {isPositiveDecimal(r.withdrawable) && (
                        <button
                          className="button ghost small"
                          data-testid={`mark-${r.month}`}
                          onClick={() =>
                            setModal({
                              tone: "warning",
                              kicker: "MANUAL BOOKKEEPING",
                              title: `Mark ${formatUsd(r.withdrawable)} as withdrawn for ${r.month}?`,
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
        )}
      </div>

      <div className="panel withdrawal-rule">
        <ShieldCheck size={22} />
        <div>
          <p className="kicker">WITHDRAWAL RULE</p>
          <h2>Manual bookkeeping only</h2>
          <p>
            Withdrawable = max(0, realized net profit) × 10%. CryptoPilot never moves funds and the
            Binance API key never has withdrawal permission.
          </p>
        </div>
      </div>

      {modal && <ConfirmModal modal={modal} onClose={() => setModal(null)} />}
    </div>
  );
}
