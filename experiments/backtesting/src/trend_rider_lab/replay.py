"""Legacy CLI compatibility: shared replay implementation, no duplicate execution model."""

from strategy_runtime.replay import (
    ReplayConfig as ReplayConfig,
    Position as Position,
    ReplayResult as ReplayResult,
    ReferenceReplayEngine as ReferenceReplayEngine,
    PluginReplayEngine as PluginReplayEngine,
    _exit_reason as _exit_reason,
    _production_tp_qty as _production_tp_qty,
    _monthly_returns as _monthly_returns,
    _max_drawdown as _max_drawdown,
    _sharpe as _sharpe,
    run_replay as run_replay,
    config_dict as config_dict,
)
