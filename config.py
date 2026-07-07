"""Configuration for Product 1 — every threshold and weight is named and tunable (no magic numbers)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SaasThresholds:
    seat_util_floor: float = 0.60          # below → HIGH flag
    seat_util_critical: float = 0.50       # below (with stale sponsor) → CRITICAL flag
    renewal_warn: int = 120                # days
    renewal_critical: int = 90             # days
    adoption_floor: float = 0.40           # below → MEDIUM flag
    sponsor_stale_days: int = 90
    seat_decline_sat: float = 0.20         # QoQ seat drop that saturates the decline factor
    nps_risk_floor: float = 40.0           # nps ≥ this → 0 risk
    nps_risk_ceiling: float = -20.0        # nps ≤ this → full risk
    nps_trend_drop: float = -0.15          # QoQ nps drop → HIGH flag
    ttv_target_days: int = 90
    ttv_window_days: int = 120
    first_year_months: int = 12
    min_trend_points: int = 4              # series length needed for a trend factor
    escalation_count: int = 2              # N flags in a tier escalate one tier up

    # Cadence alert thresholds (fractional decline that triggers each horizon).
    wow_alert: float = -0.10               # week-over-week decline → escalate immediately
    mom_alert: float = -0.05               # month-over-month decline → monthly review
    qoq_alert: float = -0.05               # quarter-over-quarter decline → strategic review

    # Score weights (sum to 1.0); a missing factor contributes 0 (NOT renormalized).
    w_seat: float = 0.25
    w_adoption: float = 0.20
    w_nps: float = 0.15
    w_sponsor: float = 0.15
    w_decline: float = 0.15
    w_ttv: float = 0.10


@dataclass
class SaasConfig:
    today: str = "2026-06-30"              # configurable for reproducible / back-tested runs
    max_data_age_days: int = 45            # freshness SLA
    allow_stale: bool = False              # stale data hard-fails unless explicitly allowed
    thresholds: SaasThresholds = field(default_factory=SaasThresholds)
    # Per-segment confidence thresholds for the low_confidence flag.
    min_coverage: dict = field(default_factory=lambda: {"enterprise": 0.9, "smb": 0.5, "default": 0.6})

    def coverage_threshold(self, segment: str) -> float:
        return self.min_coverage.get((segment or "").lower(), self.min_coverage["default"])
