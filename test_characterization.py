#!/usr/bin/env python3
"""
Characterization + signal-selection tests for the registry-driven churn engine.
Pins verdicts over ALL signals and verifies that PICKING signals changes the calculation.
Run: python test_characterization.py
"""
from __future__ import annotations

import sys

from config import SaasConfig
from adapter import load
from churn import assess, all_signal_keys

CSV = "subscription_accounts.csv"

GOLDEN = {
    "ACME": {"band": "LOW", "escalated": False, "risk_score": 0.6, "coverage": 1.0},
    "BETA": {"band": "CRITICAL", "escalated": False, "risk_score": 66.6, "coverage": 1.0},
    "GAMMA": {"band": "HIGH", "escalated": True, "risk_score": 4.3, "coverage": 1.0},
    "DELTA": {"band": "LOW", "escalated": False, "risk_score": 0.3, "coverage": 0.43},
}
TOL = 1e-6


def main() -> None:
    cfg = SaasConfig()
    accts = {a["account_name"]: a for a in load(CSV, cfg, report_path="/tmp/p1_test_vr.json")["accounts"]}
    passed = failed = 0

    def check(label, got, want):
        nonlocal passed, failed
        ok = (got == want) if not isinstance(want, float) else (got is not None and abs(got - want) <= TOL)
        if ok:
            passed += 1
        else:
            failed += 1
            print(f"  FAIL  {label}: got {got!r}, want {want!r}")

    # ── All-signals characterization ────────────────────────────────────────
    for name, exp in GOLDEN.items():
        v = assess(accts[name], cfg)
        for field, want in exp.items():
            check(f"{name}.{field}", v[field], want)

    check("registry size", len(all_signal_keys()), 30)

    # ── Picking changes the calc: drop GAMMA's two MEDIUM signals → LOW ─────
    g_all = assess(accts["GAMMA"], cfg)
    sub = [s for s in g_all["signals_used"] if s not in ("feature_adoption", "time_to_value")]
    check("GAMMA HIGH with all signals", g_all["band"], "HIGH")
    check("GAMMA drops to LOW without the 2 MEDIUM signals", assess(accts["GAMMA"], cfg, sub)["band"], "LOW")

    # ── Coverage reflects the selection ─────────────────────────────────────
    pick = assess(accts["ACME"], cfg, ["seat_utilization", "feature_adoption"])  # weights 0.09 + 0.06
    check("coverage = sum of picked weights", pick["coverage"], 0.15)

    # ── Deselect everything → UNKNOWN, no score ─────────────────────────────
    none = assess(accts["ACME"], cfg, [])
    check("no signals → UNKNOWN band", none["band"], "UNKNOWN")
    check("no signals → coverage 0", none["coverage"], 0.0)
    check("no signals → score None", none["risk_score"], None)

    # ── Partial data lowers coverage + flags low confidence ─────────────────
    delta = assess(accts["DELTA"], cfg)
    check("DELTA partial coverage < 1", delta["coverage"] < 1.0, True)
    check("DELTA flagged low confidence", delta["low_confidence"], True)

    print(f"\n{passed}/{passed + failed} passed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
