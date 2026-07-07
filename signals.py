"""Churn-signal registry for Product 1.

Every SaaS churn signal is a first-class, toggleable entry here. Each signal declares its category,
weight (weights across ALL signals sum to 1.0), a `kind` that says how to turn its data into a risk
factor (0..1) + rule-tree flags, the data field it reads, and kind-specific params (all thresholds
named — no magic numbers). A signal whose data is absent (or that the user deselects) contributes
nothing and simply lowers coverage — the graceful-degradation design.

`evaluate(signal, account, cfg)` -> (factor|None, flags) where flags is a list of (tier, reason).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

TIER_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


@dataclass
class Signal:
    key: str
    category: str
    label: str
    weight: float
    kind: str
    field: str
    params: dict = field(default_factory=dict)


# ── the full taxonomy (weights sum to 1.0) ─────────────────────────────────────
REGISTRY: list[Signal] = [
    # A. Product engagement (0.45)
    Signal("seat_utilization", "Engagement", "Seat utilization", 0.09, "seat_util", "seats_active_series", {"floor": 0.60, "licensed_field": "seats_licensed"}),
    Signal("user_retention", "Engagement", "Per-user retention", 0.09, "ratio_low", "user_retention_series", {"floor": 0.80}),
    Signal("stickiness", "Engagement", "Stickiness (DAU/MAU)", 0.05, "ratio_low", "dau_mau_ratio", {"floor": 0.30, "tier": "MEDIUM"}),
    Signal("login_recency", "Engagement", "Login recency (days)", 0.05, "days_high", "days_since_last_login", {"good": 3, "bad": 30, "flag_above": 14}),
    Signal("feature_adoption", "Engagement", "Feature adoption breadth", 0.06, "ratio_low", "feature_adoption_pct", {"floor": 0.40, "tier": "MEDIUM"}),
    Signal("advanced_adoption", "Engagement", "Advanced feature adoption", 0.04, "ratio_low", "advanced_adoption_pct", {"floor": 0.30, "tier": "MEDIUM"}),
    Signal("usage_trend", "Engagement", "Core-usage trend", 0.05, "trend_decline", "usage_action_series", {"sat": 0.20, "drop": -0.15}),
    Signal("time_to_value", "Engagement", "Time-to-value", 0.02, "ttv", "ttv_days", {"target": 90, "window": 120, "start_field": "contract_start"}),
    # B. Relationship & CS (0.15)
    Signal("sponsor_recency", "Relationship", "Exec-sponsor recency", 0.06, "date_stale", "sponsor_last_contact_date", {"good": 14, "bad": 120, "flag_above": 90}),
    Signal("champion_departed", "Relationship", "Champion departed", 0.05, "bool_risk", "champion_departed", {"risk_when": True, "tier": "HIGH"}),
    Signal("multithreading", "Relationship", "Multi-threading (stakeholders)", 0.02, "count_low", "engaged_stakeholders", {"min_good": 3, "flag_below": 2, "tier": "MEDIUM"}),
    Signal("qbr_cadence", "Relationship", "Business-review cadence (days)", 0.02, "days_high", "days_since_last_qbr", {"good": 30, "bad": 180, "flag_above": 120, "tier": "MEDIUM"}),
    # C. Voice + support (0.15)
    Signal("nps", "Voice & Support", "NPS", 0.05, "nps", "nps_series", {"floor": 40, "ceiling": -20, "flag_below": 0}),
    Signal("csat", "Voice & Support", "CSAT", 0.03, "ratio_low", "csat", {"floor": 0.70, "tier": "MEDIUM"}),
    Signal("open_tickets", "Voice & Support", "Open tickets", 0.02, "count_high", "open_tickets", {"good": 2, "bad": 30, "flag_above": 15, "tier": "MEDIUM"}),
    Signal("critical_tickets", "Voice & Support", "Unresolved critical tickets", 0.02, "count_high", "critical_open", {"good": 0, "bad": 5, "flag_above": 1, "tier": "HIGH"}),
    Signal("resolution_time", "Voice & Support", "Avg resolution days", 0.02, "count_high", "avg_resolution_days", {"good": 1, "bad": 10, "flag_above": 7, "tier": "MEDIUM"}),
    Signal("ticket_trend", "Voice & Support", "Ticket-volume trend", 0.01, "trend_increase", "ticket_series", {"sat": 0.5, "rise": 0.3, "tier": "MEDIUM"}),
    # E. Commercial / financial (0.15)
    Signal("payment_health", "Commercial", "Payment overdue (days)", 0.05, "days_high", "days_payment_overdue", {"good": 0, "bad": 60, "flag_above": 15, "tier": "HIGH"}),
    Signal("contraction_history", "Commercial", "Recent contraction", 0.04, "gt_zero_risk", "contraction_arr", {"tier": "HIGH"}),
    Signal("discount_dependency", "Commercial", "Discount dependency", 0.02, "pct_high", "discount_pct", {"sat": 0.5, "flag_at": 0.3, "tier": "MEDIUM"}),
    Signal("renewal_price_increase", "Commercial", "Renewal price increase", 0.02, "pct_high", "renewal_price_change_pct", {"sat": 0.3, "flag_at": 0.1, "tier": "MEDIUM"}),
    Signal("contract_term", "Commercial", "No auto-renew", 0.02, "bool_risk", "auto_renew", {"risk_when": False, "tier": "MEDIUM"}),
    # F/G/H. Value, external, behavioral (0.10)
    Signal("goal_attainment", "Value & Risk", "Goal / ROI attainment", 0.03, "ratio_low", "goal_attainment_pct", {"floor": 0.60}),
    Signal("onboarding_complete", "Value & Risk", "Onboarding incomplete", 0.02, "bool_risk", "onboarding_complete", {"risk_when": False, "tier": "MEDIUM"}),
    Signal("external_risk", "Value & Risk", "Company-health event", 0.02, "bool_risk", "external_risk_flag", {"risk_when": True, "tier": "HIGH"}),
    Signal("admin_change", "Value & Risk", "Admin/owner change", 0.01, "bool_risk", "admin_changed", {"risk_when": True, "tier": "MEDIUM"}),
    Signal("cancellation_inquiry", "Value & Risk", "Cancellation inquiry", 0.01, "bool_risk", "cancellation_inquiry", {"risk_when": True, "tier": "CRITICAL"}),
    Signal("seat_reduction", "Value & Risk", "Seat-reduction request", 0.005, "bool_risk", "seat_reduction_requested", {"risk_when": True, "tier": "HIGH"}),
    Signal("competitor_eval", "Value & Risk", "Competitor evaluation", 0.005, "bool_risk", "competitor_eval", {"risk_when": True, "tier": "HIGH"}),
]

REGISTRY_BY_KEY = {s.key: s for s in REGISTRY}
CATEGORIES = list(dict.fromkeys(s.category for s in REGISTRY))


# ── coercion helpers (blank / missing → None) ──────────────────────────────────
def _num(a: dict, k: str) -> Optional[float]:
    v = a.get(k)
    if v is None or (isinstance(v, str) and v.strip() == ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _series(a: dict, k: str) -> Optional[list[float]]:
    v = a.get(k)
    if v is None:
        return None
    if isinstance(v, (list, tuple)):
        return [float(x) for x in v] or None
    if isinstance(v, str) and v.strip():
        try:
            return [float(x) for x in v.split(";") if x.strip() != ""] or None
        except ValueError:
            return None
    return None


def _bool(a: dict, k: str) -> Optional[bool]:
    v = a.get(k)
    if v is None or (isinstance(v, str) and v.strip() == ""):
        return None
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("true", "1", "yes", "y")


def _days_since(a: dict, k: str, today: datetime) -> Optional[float]:
    v = a.get(k)
    if not v:
        return None
    try:
        return (today - datetime.strptime(str(v).strip(), "%Y-%m-%d")).days
    except ValueError:
        return None


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _sd(n: float, d: float) -> float:
    """Safe divide — a zero scaling range yields 0 risk instead of crashing."""
    return n / d if d else 0.0


def _qoq(series: list[float]) -> float:
    n = len(series)
    half = n // 2
    prior, latest = sum(series[:half]), sum(series[-half:])
    return (latest - prior) / prior if prior else 0.0


# ── evaluation ─────────────────────────────────────────────────────────────────
def evaluate(sig: Signal, a: dict, cfg) -> tuple[Optional[float], list[tuple[str, str]]]:
    p = sig.params
    today = datetime.strptime(cfg.today, "%Y-%m-%d")
    tier = p.get("tier", "HIGH")

    if sig.kind == "seat_util":
        s = _series(a, sig.field)
        licensed = _num(a, p.get("licensed_field", "seats_licensed"))
        if s is None or not licensed:
            return None, []
        v = min(1.0, s[-1] / licensed)
        flags = [(tier, f"{sig.label} {v:.0%} < {p['floor']:.0%}")] if v < p["floor"] else []
        return _clamp(_sd(p["floor"] - v, p["floor"])), flags

    if sig.kind == "ratio_low":
        s = _series(a, sig.field)
        v = s[-1] if s else _num(a, sig.field)
        if v is None:
            return None, []
        flags = [(tier, f"{sig.label} {v:.0%} < {p['floor']:.0%}")] if v < p["floor"] else []
        return _clamp(_sd(p["floor"] - v, p["floor"])), flags

    if sig.kind == "nps":
        s = _series(a, sig.field)
        v = s[-1] if s else _num(a, sig.field)
        if v is None:
            return None, []
        flags = [(tier, f"NPS {v:.0f} < {p['flag_below']}")] if v < p["flag_below"] else []
        return _clamp(_sd(p["floor"] - v, p["floor"] - p["ceiling"])), flags

    if sig.kind in ("days_high", "count_high"):
        v = _num(a, sig.field)
        if v is None:
            return None, []
        flags = [(tier, f"{sig.label} = {v:g} (> {p['flag_above']})")] if v > p["flag_above"] else []
        return _clamp(_sd(v - p["good"], p["bad"] - p["good"])), flags

    if sig.kind == "date_stale":
        v = _days_since(a, sig.field, today)
        if v is None:
            return None, []
        flags = [(tier, f"{sig.label}: {v:.0f}d (> {p['flag_above']}d)")] if v > p["flag_above"] else []
        return _clamp(_sd(v - p["good"], p["bad"] - p["good"])), flags

    if sig.kind == "count_low":
        v = _num(a, sig.field)
        if v is None:
            return None, []
        flags = [(tier, f"{sig.label} = {v:g} (< {p['flag_below']})")] if v < p["flag_below"] else []
        return _clamp(_sd(p["min_good"] - v, p["min_good"])), flags

    if sig.kind == "bool_risk":
        b = _bool(a, sig.field)
        if b is None:
            return None, []
        risky = (b == p["risk_when"])
        return (1.0 if risky else 0.0), ([(tier, sig.label)] if risky else [])

    if sig.kind == "gt_zero_risk":
        v = _num(a, sig.field)
        if v is None:
            return None, []
        risky = v > 0
        return (1.0 if risky else 0.0), ([(tier, f"{sig.label} (${v:,.0f})")] if risky else [])

    if sig.kind == "pct_high":
        v = _num(a, sig.field)
        if v is None:
            return None, []
        flags = [(tier, f"{sig.label} {v:.0%} (≥ {p['flag_at']:.0%})")] if v >= p["flag_at"] else []
        return _clamp(_sd(v, p["sat"])), flags

    if sig.kind in ("trend_decline", "trend_increase"):
        s = _series(a, sig.field)
        if s is None or len(s) < cfg.thresholds.min_trend_points:
            return None, []
        q = _qoq(s)
        if sig.kind == "trend_decline":
            flags = [(tier, f"{sig.label} {q:+.0%} (≤ {p['drop']:+.0%})")] if q <= p["drop"] else []
            return _clamp(_sd(-q, p["sat"])), flags
        flags = [(tier, f"{sig.label} {q:+.0%} (≥ {p['rise']:+.0%})")] if q >= p["rise"] else []
        return _clamp(_sd(q, p["sat"])), flags

    if sig.kind == "ttv":
        v = _num(a, sig.field)
        cs = a.get(p.get("start_field", "contract_start"))
        if v is None or not cs:
            return None, []
        try:
            months = (today.year - datetime.strptime(str(cs), "%Y-%m-%d").year) * 12 + \
                     (today.month - datetime.strptime(str(cs), "%Y-%m-%d").month)
        except ValueError:
            return None, []
        if months > cfg.thresholds.first_year_months:
            return 0.0, []
        risk = _clamp(_sd(v - p["target"], p["window"]))
        return risk, ([("MEDIUM", f"slow time-to-value ({v:g}d)")] if risk > 0 else [])

    return None, []
