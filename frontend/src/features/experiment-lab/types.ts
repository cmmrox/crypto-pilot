export interface ParameterDefinition {
  key: string;
  label: string;
  unit: string;
  default: string;
  minimum: string;
  maximum: string;
  step: string;
}

export interface Strategy {
  id: string;
  name: string;
  intervals: string[];
  parameters: ParameterDefinition[];
}

export interface StudyConfig {
  name: string;
  strategy_id: string;
  dataset_id: string;
  start: string;
  end: string;
  interval: string;
  fidelity?: "CANDLE_REPLAY" | "TRADE_REPLAY";
  initial_capital: string;
  parameters: Record<string, string>;
  pinned: string[];
}

export interface Metrics {
  net_profit: string;
  final_equity: string;
  max_drawdown: string;
  worst_month: string;
  trade_count: number;
  full_months: number;
  profitable_month_ratio: string;
  monthly: { month: string; profit: string; return: string; full: boolean }[];
  suitable_for_live: boolean;
  ineligibility_reasons: string[];
  fidelity: string;
  winning_trades: number;
  losing_trades: number;
  profit_factor: string | null;
  total_fees: string;
  total_funding: string;
  open_net_pnl: string;
  funding_mark_fallbacks: number;
}

export interface Iteration {
  id: string;
  ordinal: number;
  mode: string;
  status: string;
  parameters: Record<string, string>;
  advice: { hypothesis: string; uncertainty: string; falsification: string } | null;
  result: { artifact_id: string; metrics: Metrics } | null;
  review: {
    summary: string;
    lesson: string;
    counterevidence: string;
    next_hypothesis: string;
  } | null;
  error: string | null;
}

export interface Study {
  id: string;
  highest_profit_iteration_id?: string | null;
  highest_profit_iteration?: Iteration | null;
  total_iterations?: number;
  completed_iterations?: number;
  active?: boolean;
  next_cursor?: number | null;
  config: StudyConfig;
  iterations?: Iteration[];
  lessons?: unknown[];
}
