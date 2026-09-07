import { useState } from "react";
import { ParameterEditor } from "./ParameterEditor";
import type { Strategy, StudyConfig } from "./types";

/** Study drafts own their parameters separately from existing manual iterations. */
export function NewStudyForm({
  strategy,
  onSubmit,
  pending,
}: {
  strategy: Strategy;
  onSubmit: (config: StudyConfig) => void;
  pending: boolean;
}) {
  const [parameters, setParameters] = useState<Record<string, string>>(() =>
    Object.fromEntries(strategy.parameters.map((field) => [field.key, field.default])),
  );
  const [pinned, setPinned] = useState<string[]>([]);
  const defaults = Object.fromEntries(
    strategy.parameters.map((field) => [field.key, field.default]),
  );

  function submitStudy(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const config: StudyConfig = {
      name: String(form.get("name")),
      strategy_id: strategy.id,
      dataset_id: String(form.get("dataset")),
      start: `${form.get("start")}T00:00:00Z`,
      end: `${form.get("end")}T00:00:00Z`,
      interval: String(form.get("interval")),
      fidelity: form.get("fidelity") === "TRADE_REPLAY" ? "TRADE_REPLAY" : "CANDLE_REPLAY",
      initial_capital: String(form.get("capital")),
      parameters: { ...defaults, ...parameters },
      pinned,
    };
    onSubmit(config);
  }

  return (
    <form className="lab-panel" onSubmit={submitStudy}>
      <h2>New {strategy.name} study</h2>
      <p>
        Study inputs are frozen for fair comparison. Changing dates, timeframe or seed creates a
        separate study. Prepare a verified Binance dataset using the Lab data command.
      </p>
      <div className="lab-form-grid">
        <label>
          Study name
          <input name="name" required maxLength={100} />
        </label>
        <label>
          Binance dataset ID
          <input name="dataset" required pattern="[a-f0-9]{64}" />
        </label>
        <label>
          Start date (UTC)
          <input type="date" name="start" required />
        </label>
        <label>
          End date (UTC, exclusive)
          <input type="date" name="end" required />
        </label>
        <label>
          Timeframe
          <select name="interval">
            {strategy.intervals.map((interval) => (
              <option key={interval}>{interval}</option>
            ))}
          </select>
        </label>
        <label>
          Initial capital (USDT)
          <input type="number" name="capital" min="1" step="0.01" defaultValue="100" required />
        </label>
        <label>
          Execution evidence
          <select name="fidelity">
            <option value="CANDLE_REPLAY">Candle replay · faster screening</option>
            <option value="TRADE_REPLAY">Actual Binance trades · large download</option>
          </select>
        </label>
      </div>
      <details>
        <summary>Existing strategy parameters and advisor pins</summary>
        <ParameterEditor
          definitions={strategy.parameters}
          values={parameters}
          pinned={pinned}
          onChange={setParameters}
          onPin={setPinned}
        />
      </details>
      <button type="submit" disabled={pending}>
        {pending ? "Creating…" : "Create study"}
      </button>
    </form>
  );
}
