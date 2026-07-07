"""Portfolio lagging KPIs for subscription SaaS — GRR / NRR / logo churn over the renewal cohort."""
from __future__ import annotations

from typing import Any


def _arr(a: dict[str, Any], field: str) -> float:
    """Tolerant read of an ARR-movement field: absent/blank → 0.0 (a source may not supply it)."""
    v = a.get(field, 0)
    try:
        return float(v) if v not in ("", None) else 0.0
    except (TypeError, ValueError):
        return 0.0


def portfolio_kpis(accounts: list[dict[str, Any]]) -> dict[str, Any]:
    """Cohort = accounts active at period start (prior_period_arr > 0). Guards against an empty cohort
    and against sources that don't supply the renewal-movement fields (→ KPIs return None)."""
    cohort = [a for a in accounts if _arr(a, "prior_period_arr") > 0]
    s = sum(_arr(a, "prior_period_arr") for a in cohort)
    if not cohort or s <= 0:
        return {"grr": None, "nrr": None, "logo_churn": None, "cohort_size": len(cohort)}

    contraction = sum(_arr(a, "contraction_arr") for a in cohort)
    churned = sum(_arr(a, "churned_arr") for a in cohort)
    expansion = sum(_arr(a, "expansion_arr") for a in cohort)
    churned_logos = sum(1 for a in cohort if _arr(a, "churned_arr") > 0)

    return {
        "grr": round((s - contraction - churned) / s, 4),
        "nrr": round((s - contraction - churned + expansion) / s, 4),
        "logo_churn": round(churned_logos / len(cohort), 4),
        "cohort_size": len(cohort),
    }
