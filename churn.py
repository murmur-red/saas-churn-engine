"""Deterministic subscription churn verdict (rules only, no model calls).

Registry-driven: the churn calculation runs over a USER-SELECTABLE set of signals (see signals.py).
Only signals the user includes AND that have data contribute — each yields a risk factor (0..1) and
optional rule-tree flags. Score is fixed-weight (missing/excluded factor contributes 0, not
renormalized) with a reported coverage; band comes from the flags with combinatorial escalation and a
renewal-proximity amplifier. Band is the authoritative triage verdict; score is a comparable rank.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Optional

from core import scoring
from signals import REGISTRY, TIER_RANK, evaluate

RANK_TIER = {v: k for k, v in TIER_RANK.items()}


def all_signal_keys() -> list[str]:
    return [s.key for s in REGISTRY]


def assess(account: dict[str, Any], config, enabled: Optional[Iterable[str]] = None) -> dict[str, Any]:
    """Runs the churn calculation over the selected signals (default: all)."""
    enabled_set = set(enabled) if enabled is not None else set(all_signal_keys())

    reasons: list[str] = []
    flags: list[tuple[str, str]] = []          # (tier, reason)
    weighted_risk = 0.0
    coverage = 0.0
    used, unavailable = [], []

    for sig in REGISTRY:
        if sig.key not in enabled_set:
            continue
        factor, sig_flags = evaluate(sig, account, config)
        if factor is None:
            unavailable.append(sig.key)
            reasons.append(f"unknown: {sig.label} (no data)")
            continue
        used.append(sig.key)
        coverage += sig.weight
        weighted_risk += sig.weight * factor
        for tier, reason in sig_flags:
            flags.append((tier, reason))
            reasons.append(f"[{tier}] {reason}")

    risk_score = round(100 * weighted_risk, 1) if coverage > 0 else None

    # ── Band: highest fired tier + combinatorial escalation + renewal amplifier ──
    if not used:
        band, escalated = "UNKNOWN", False
    else:
        by_tier = {"MEDIUM": 0, "HIGH": 0, "CRITICAL": 0}
        for tier, _ in flags:
            by_tier[tier] = by_tier.get(tier, 0) + 1
        direct = "CRITICAL" if by_tier["CRITICAL"] else "HIGH" if by_tier["HIGH"] else \
                 "MEDIUM" if by_tier["MEDIUM"] else "LOW"
        rank = TIER_RANK[direct]
        esc = config.thresholds.escalation_count
        if by_tier["MEDIUM"] >= esc:
            rank = max(rank, TIER_RANK["HIGH"])
        if by_tier["HIGH"] >= esc:
            rank = max(rank, TIER_RANK["CRITICAL"])
        # Renewal amplifier: problems close to renewal are more urgent.
        days_to_renewal = _days_to_renewal(account, config)
        renewal_imminent = days_to_renewal is not None and days_to_renewal <= config.thresholds.renewal_critical
        if renewal_imminent and rank >= TIER_RANK["MEDIUM"]:
            rank = min(TIER_RANK["CRITICAL"], rank + 1)
        escalated = rank > TIER_RANK[direct]
        if escalated:
            reasons.append(f"escalated: {by_tier['HIGH']} HIGH / {by_tier['MEDIUM']} MEDIUM flags"
                           + (" + renewal imminent" if renewal_imminent else ""))
        band = RANK_TIER[rank]

    booked = float(account.get("booked_arr", 0) or 0)
    exposure = round(scoring.expected_value(risk_score / 100, booked)) if risk_score is not None else None
    low_conf = (coverage < config.coverage_threshold(account.get("segment", ""))) if coverage > 0 else True

    return {
        "account_name": account.get("account_name", "?"),
        "segment": account.get("segment", ""),
        "band": band,
        "escalated": escalated,
        "reasons": reasons,
        "risk_score": risk_score,
        "coverage": round(coverage, 3),
        "low_confidence": low_conf,
        "risk_weighted_exposure": exposure,
        "signals_used": used,
        "signals_unavailable": unavailable,
    }


def _days_to_renewal(account: dict, config) -> Optional[int]:
    v = account.get("renewal_date")
    if not v:
        return None
    try:
        d = (datetime.strptime(str(v), "%Y-%m-%d") - datetime.strptime(config.today, "%Y-%m-%d")).days
        return max(0, d)
    except ValueError:
        return None
