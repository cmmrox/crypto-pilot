"""Resolve execution policy without rewriting historical release semantics."""

from strategy_runtime.manifest import ExecutionSpec

from app.strategies import get_strategy


def execution_policy(strategy: str, release: str) -> ExecutionSpec:
    # Release 1.1 continues using its original mark-price protection. Adoption of
    # the new execution contract applies to entries tagged 1.2, never silently to
    # a carried position from an earlier release.
    if strategy == "atlas_dual_v1_4h" and release == "1.2":
        return get_strategy(strategy).manifest.execution
    return ExecutionSpec()
