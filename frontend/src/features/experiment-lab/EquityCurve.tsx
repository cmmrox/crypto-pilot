import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { labApi } from "./api";

/** Load detailed evidence only on demand; list polling stays compact. */
export function EquityCurve({ iterationId, interval }: { iterationId: string; interval: string }) {
  const [visible, setVisible] = useState(false);
  const evidence = useQuery({
    queryKey: ["lab-equity", iterationId],
    queryFn: () => labApi.artifact(iterationId),
    enabled: visible,
    staleTime: Infinity,
  });
  const minutes = interval === "4h" ? 240 : interval === "1h" ? 60 : 30;
  // Runtime rows are indexed by candle opening time. Equity is valued at close.
  // Number conversion is chart rendering only; the immutable ledger stays Decimal.
  const points =
    evidence.data?.equity.map((point, index) => ({
      index,
      time: new Date(
        Date.parse(point.dt) + (point.kind === "INITIAL_CAPITAL" ? 0 : minutes * 60_000),
      ).toISOString(),
      equity: Number(point.equity),
    })) ?? [];
  return (
    <div>
      <button onClick={() => setVisible(!visible)} aria-expanded={visible}>
        {visible ? "Hide equity curve" : "View equity curve"}
      </button>
      {visible && evidence.isPending && <p role="status">Loading immutable equity evidence…</p>}
      {visible && evidence.error && <p role="alert">{evidence.error.message}</p>}
      {visible && evidence.data && (
        <figure aria-label="Historical equity curve including initial capital">
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={points} margin={{ left: 10, right: 15, top: 10, bottom: 10 }}>
              <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
              <XAxis
                dataKey="index"
                interval="preserveStartEnd"
                stroke="#a9bdc8"
                tickFormatter={(index: number) => points[index]?.time.slice(0, 10) ?? ""}
                minTickGap={60}
              />
              <YAxis
                stroke="#a9bdc8"
                domain={["auto", "auto"]}
                tickFormatter={(value: number) => value.toFixed(0)}
              />
              <Tooltip
                labelFormatter={(index) => points[Number(index)]?.time ?? ""}
                formatter={(value) => [`${Number(value).toFixed(2)} USDT`, "Equity"]}
              />
              <Line dataKey="equity" stroke="#60a5fa" dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
          <figcaption>
            Initial capital and each candle-close valuation, UTC. Simulated equity includes open
            positions; future monthly profits are not guaranteed.
          </figcaption>
        </figure>
      )}
    </div>
  );
}
