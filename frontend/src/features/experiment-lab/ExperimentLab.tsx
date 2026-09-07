import { formatDecimal } from "../../utils/decimal";
import { useEffect, useState } from "react";
import {
  QueryClient,
  QueryClientProvider,
  useMutation,
  useInfiniteQuery,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { labApi } from "./api";
import { ParameterEditor } from "./ParameterEditor";
import { IterationList } from "./IterationList";
import { NewStudyForm } from "./NewStudyForm";
import "./lab.css";

function LabScreen() {
  const cache = useQueryClient();
  const [selected, setSelected] = useState(() => sessionStorage.getItem("cp-lab-study") ?? "");
  useEffect(() => {
    sessionStorage.setItem("cp-lab-study", selected);
  }, [selected]);
  const [before, setBefore] = useState<number>();
  const [creating, setCreating] = useState(false);
  const [parameters, setParameters] = useState<Record<string, string>>({});
  const [manual, setManual] = useState(false);
  const [skill, setSkill] = useState("");
  const strategies = useQuery({ queryKey: ["lab-strategies"], queryFn: labApi.strategies });
  const studies = useInfiniteQuery({
    queryKey: ["lab-studies"],
    queryFn: ({ pageParam }) => labApi.studies(pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => (lastPage.length === 50 ? lastPage.at(-1)?.id : undefined),
  });
  const study = useQuery({
    queryKey: ["lab-study", selected, before],
    queryFn: () => labApi.study(selected, before),
    enabled: !!selected,
    refetchInterval: (query) => (query.state.data?.active ? 3000 : 30000),
  });
  const refresh = () => {
    setBefore(undefined);
    void cache.invalidateQueries({ queryKey: ["lab-study", selected] });
  };
  const create = useMutation({
    mutationFn: labApi.create,
    onSuccess: (value) => {
      setSelected(value.id);
      setBefore(undefined);
      setManual(false);
      setSkill("");
      setCreating(false);
      void cache.invalidateQueries({ queryKey: ["lab-studies"] });
    },
  });
  const run = useMutation({
    mutationFn: (source?: string) =>
      labApi.run(
        selected,
        source ? "REPRODUCE" : manual ? "MANUAL" : "ADVISED",
        parameters,
        source,
      ),
    onSuccess: refresh,
  });
  const cancel = useMutation({ mutationFn: labApi.cancel, onSuccess: refresh });
  const retryReview = useMutation({ mutationFn: labApi.retryReview, onSuccess: refresh });
  const download = useMutation({
    mutationFn: labApi.candidate,
    onSuccess: (value) => {
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }),
      );
      const link = document.createElement("a");
      link.href = url;
      link.download = "research-candidate.json";
      link.click();
      URL.revokeObjectURL(url);
    },
  });
  const loadSkill = useMutation({
    mutationFn: () => labApi.skill(selected),
    onSuccess: (value) => setSkill(value.markdown),
  });
  const iterations = study.data?.iterations ?? [];
  const active = study.data?.active ?? false;
  const best = study.data?.highest_profit_iteration;
  const strategy = strategies.data?.[0];
  const error =
    strategies.error ??
    studies.error ??
    study.error ??
    create.error ??
    run.error ??
    cancel.error ??
    loadSkill.error ??
    retryReview.error ??
    download.error;

  return (
    <section className="lab-page">
      <header className="lab-heading">
        <div>
          <p className="kicker">RESEARCH · NOT LIVE TRADING</p>
          <h1>Experiment Lab</h1>
          <p>Compare strategy parameters, one measured iteration at a time.</p>
        </div>
        <button
          disabled={!strategy}
          onClick={() => {
            setCreating(!creating);
          }}
        >
          New study
        </button>
      </header>
      {error && (
        <div className="lab-error" role="alert">
          {error.message}
          <button
            onClick={() => {
              void strategies.refetch();
              void studies.refetch();
              if (selected) void study.refetch();
            }}
          >
            Retry connection
          </button>
        </div>
      )}
      {strategies.isPending && <p role="status">Connecting to Experiment Lab…</p>}
      <label className="lab-selector">
        Strategy study
        <select
          value={selected}
          onChange={(event) => {
            setSelected(event.target.value);
            setBefore(undefined);
            setSkill("");
            setManual(false);
          }}
        >
          <option value="">Select a study</option>
          {studies.data?.pages.flat().map((item) => (
            <option value={item.id} key={item.id}>
              {item.config.name} · {item.config.interval}
            </option>
          ))}
        </select>
      </label>
      {studies.hasNextPage && (
        <button disabled={studies.isFetchingNextPage} onClick={() => void studies.fetchNextPage()}>
          Load older studies
        </button>
      )}
      {creating && strategy && (
        <NewStudyForm
          strategy={strategy}
          onSubmit={(config) => create.mutate(config)}
          pending={create.isPending}
        />
      )}
      {study.data && (
        <>
          <div className="lab-summary">
            <div>
              <small>Strategy</small>
              <strong>{study.data.config.name}</strong>
              <span>{study.data.config.interval} · BTCUSDT USD-M</span>
              <small>
                {study.data.config.start.slice(0, 10)} → {study.data.config.end.slice(0, 10)} UTC
                (end exclusive)
              </small>
            </div>
            <div>
              <small>Completed iterations</small>
              <strong>{study.data.completed_iterations ?? 0}</strong>
              <span>{study.data.total_iterations ?? 0} total attempts</span>
            </div>
            <div>
              <small>Highest observed profit</small>
              <strong>
                {best ? `${formatDecimal(best.result!.metrics.net_profit)} USDT` : "No result yet"}
              </strong>
              <span>
                {best
                  ? `Iteration #${best.ordinal} · exposed historical data`
                  : "Run your baseline"}
              </span>
            </div>
            <div>
              <small>Recommended for live</small>
              <strong>None verified</strong>
              <span>Separate validation required</span>
            </div>
          </div>
          <div className="lab-panel">
            <div className="lab-actions">
              <button disabled={active || run.isPending} onClick={() => run.mutate(undefined)}>
                {run.isPending
                  ? "Starting…"
                  : active
                    ? "Iteration in progress"
                    : study.data.total_iterations
                      ? "Run next iteration"
                      : "Run baseline"}
              </button>
              <label>
                <input
                  type="checkbox"
                  checked={manual}
                  disabled={active}
                  onChange={(event) => {
                    setManual(event.target.checked);
                    setParameters(study.data!.config.parameters);
                  }}
                />{" "}
                Manual parameter override
              </label>
              <button onClick={() => loadSkill.mutate()} disabled={loadSkill.isPending}>
                View learned skill
              </button>
            </div>
            <p>
              {manual
                ? "This run uses your exact edited parameters. The advisor will review its result."
                : "One click: advisor selects parameters → backtest → advisor reviews and updates evidence → stops. First run uses your unchanged baseline."}
            </p>
            {manual && strategy && (
              <ParameterEditor
                definitions={strategy.parameters}
                values={parameters}
                pinned={[]}
                onChange={setParameters}
              />
            )}
          </div>
          {skill && (
            <details open className="lab-panel">
              <summary>Versioned research skill</summary>
              <pre className="lab-skill">{skill}</pre>
            </details>
          )}
          <h2>Iteration history</h2>
          <div className="lab-actions">
            <button disabled={!before} onClick={() => setBefore(undefined)}>
              Latest iterations
            </button>
            <button
              disabled={!study.data.next_cursor || study.isFetching}
              onClick={() => setBefore(study.data!.next_cursor!)}
            >
              Older iterations
            </button>
          </div>
          <IterationList
            iterations={iterations}
            interval={study.data.config.interval}
            busy={active || run.isPending}
            onRepeat={(id) => run.mutate(id)}
            onCancel={(id) => cancel.mutate(id)}
            onRetryReview={(id) => retryReview.mutate(id)}
            onExport={(id) => download.mutate(id)}
          />
        </>
      )}
      {!selected && !creating && (
        <div className="lab-empty">
          Choose a study or create one to begin. Experiments never modify your running bot.
        </div>
      )}
      <p className="lab-disclaimer">
        Historical profits do not guarantee future returns. Losses can occur in any month. Candle
        replay is not trade-level execution verification.
      </p>
    </section>
  );
}

export function ExperimentLab() {
  const [client] = useState(() => new QueryClient({ defaultOptions: { queries: { retry: 1 } } }));
  return (
    <QueryClientProvider client={client}>
      <LabScreen />
    </QueryClientProvider>
  );
}
