"""Lossless deduplication and explicit historical-detail projection for advisor input.

Full evidence stays in the Lab's immutable decision records. Decimal strings and
input parameters are never rounded; omitted monthly detail is labeled, not inferred.
"""

from copy import deepcopy
from typing import Any


def advisor_context(context: dict[str, Any]) -> dict[str, Any]:
    projected = deepcopy(context)
    study_id = context.get("study", {}).get("id")
    history = projected.get("history", [])
    local_ids = {row["iteration_id"] for row in projected.get("lessons", [])}
    projected["strategy_lessons"] = [
        row
        for row in projected.get("strategy_lessons", [])
        if row.get("study_id") != study_id or row.get("iteration_id") not in local_ids
    ]
    # Reviews duplicate the versioned lessons; operational request keys add no evidence.
    for index, row in enumerate(history):
        for field in ("review", "request", "request_key", "created"):
            row.pop(field, None)
        advice = row.get("advice")
        if advice:
            row["advice"] = {
                key: advice[key] for key in ("hypothesis", "evidence_ids") if key in advice
            }
        if index >= 3 and row.get("result"):
            metrics = row["result"]["metrics"]
            if "monthly" in metrics:
                metrics.pop("monthly")
                row["monthly_detail"] = (
                    "Omitted from advisor projection; immutable artifact retains it. "
                    "Scalar monthly metrics remain exact."
                )
    for row in projected.get("lessons", []):
        row["content"].pop("summary", None)
    projected["advisor_context_projection"] = {
        "version": 1,
        "notes": (
            "Same-study strategy lessons deduplicated; historical reviews represented by "
            "versioned lessons; monthly rows included for latest three ancestors and current run. "
            "All supplied historical scalar metrics and parameters retained."
        ),
    }
    return projected
