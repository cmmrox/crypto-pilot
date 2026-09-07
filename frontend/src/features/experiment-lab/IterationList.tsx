import { formatDecimal, isNegativeDecimal } from "../../utils/decimal";
import type { Iteration } from "./types";
import { EquityCurve } from "./EquityCurve";

const money = formatDecimal;
const percent = (value: string) => `${(Number(value) * 100).toFixed(2)}%`;

export function IterationList({
  iterations,
  interval,
  busy,
  onRepeat,
  onCancel,
  onRetryReview,
  onExport,
}: {
  iterations: Iteration[];
  interval: string;
  busy: boolean;
  onRepeat: (id: string) => void;
  onCancel: (id: string) => void;
  onRetryReview: (id: string) => void;
  onExport: (id: string) => void;
}) {
  if (!iterations.length)
    return (
      <div className="lab-empty">
        No iterations yet. Run the baseline to measure your existing strategy before changing it.
      </div>
    );
  return (
    <div className="lab-iterations">
      {iterations.map((run) => {
        const metrics = run.result?.metrics;
        const active = !["FAILED", "COMPLETED", "CANCELLED"].includes(run.status);
        return (
          <details className="lab-iteration" key={run.id}>
            <summary>
              <strong>#{run.ordinal}</strong>
              <span>{run.status.replaceAll("_", " ")}</span>
              <span
                className={
                  metrics && isNegativeDecimal(metrics.net_profit) ? "lab-loss" : "lab-gain"
                }
              >
                {metrics ? `${money(metrics.net_profit)} USDT` : "Awaiting result"}
              </span>
              <span>{metrics ? `${percent(metrics.max_drawdown)} DD` : "—"}</span>
              <span>{metrics?.trade_count ?? "—"} trades</span>
              <span>{interval}</span>
              <span>Details</span>
            </summary>
            <div className="lab-detail">
              <p>
                <strong>Mode:</strong> {run.mode} · Run ID: <code>{run.id}</code>
              </p>
              {run.error && <p role="alert">{run.error}</p>}
              <h3>Hypothesis tested</h3>
              <p>
                {run.advice?.hypothesis ??
                  "Exact configured baseline / manually selected parameters."}
              </p>
              {run.advice && (
                <p>
                  Uncertainty: {run.advice.uncertainty}
                  <br />
                  Falsification: {run.advice.falsification}
                </p>
              )}
              <details>
                <summary>Effective input parameters</summary>
                <dl className="lab-inputs">
                  {Object.entries(run.parameters).map(([key, value]) => (
                    <div key={key}>
                      <dt>{key}</dt>
                      <dd>{value}</dd>
                    </div>
                  ))}
                </dl>
              </details>
              {metrics && (
                <>
                  <h3>Result and monthly consistency</h3>
                  <EquityCurve iterationId={run.id} interval={interval} />
                  <p>
                    Ending equity {money(metrics.final_equity)} USDT · Worst complete month{" "}
                    {percent(metrics.worst_month)} · {metrics.full_months} complete months ·{" "}
                    {metrics.fidelity}
                  </p>
                  <p>
                    Wins {metrics.winning_trades} · Losses {metrics.losing_trades} · Profit factor{" "}
                    {metrics.profit_factor === null
                      ? "Undefined (no losing trades)"
                      : money(metrics.profit_factor)}
                    <br />
                    Fees {money(metrics.total_fees)} USDT · Funding {money(metrics.total_funding)}{" "}
                    USDT · Open-position net P&amp;L {money(metrics.open_net_pnl)} USDT
                    <br />
                    Profitable complete months {percent(metrics.profitable_month_ratio)} · Funding
                    mark-price proxies {metrics.funding_mark_fallbacks}
                  </p>
                  <div className="lab-months">
                    {metrics.monthly.map((month) => (
                      <div
                        key={month.month}
                        className={isNegativeDecimal(month.profit) ? "lab-loss" : "lab-gain"}
                      >
                        <strong>{month.month}</strong>
                        <span>{money(month.profit)} USDT</span>
                        <small>{month.full ? "Full month" : "Partial month"}</small>
                      </div>
                    ))}
                  </div>
                  <p>
                    <strong>
                      Live readiness:{" "}
                      {metrics.suitable_for_live
                        ? "Eligible for separate review"
                        : "Not established"}
                    </strong>
                  </p>
                  <ul>
                    {metrics.ineligibility_reasons.map((reason) => (
                      <li key={reason}>{reason}</li>
                    ))}
                  </ul>
                </>
              )}
              <h3>What the advisor learned</h3>
              <p>{run.review?.summary ?? "Review is not available yet."}</p>
              {run.review && (
                <>
                  <p>
                    <strong>Lesson:</strong> {run.review.lesson}
                  </p>
                  <p>
                    <strong>Counterevidence:</strong> {run.review.counterevidence}
                  </p>
                  <p>
                    <strong>Next hypothesis:</strong> {run.review.next_hypothesis}
                  </p>
                  <small>
                    Observed evidence, not proof. The next parameter decision is made when you start
                    the next iteration.
                  </small>
                </>
              )}
              <div className="lab-actions">
                {metrics && (
                  <button disabled={busy} onClick={() => onRepeat(run.id)}>
                    Reproduce exact inputs
                  </button>
                )}
                {active && <button onClick={() => onCancel(run.id)}>Cancel iteration</button>}
              </div>
              <div className="lab-actions">
                {metrics && (
                  <button onClick={() => onExport(run.id)}>Export research candidate</button>
                )}
                {metrics && run.status === "FAILED" && (
                  <button disabled={busy} onClick={() => onRetryReview(run.id)}>
                    Retry review only
                  </button>
                )}
              </div>
            </div>
          </details>
        );
      })}
    </div>
  );
}
