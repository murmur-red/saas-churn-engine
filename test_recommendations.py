#!/usr/bin/env python3
"""
Tests for the cadence-driven recommendations (WoW/MoM/QoQ escalation + actions).
Run: python test_recommendations.py
"""
from __future__ import annotations

import sys

from config import SaasConfig
from adapter import load
from churn import assess
from recommendations import recommend, recommendations

passed = failed = 0


def check(label, cond):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"  FAIL  {label}")


def main() -> None:
    cfg = SaasConfig()
    accts = {a["account_name"]: a for a in load("subscription_accounts.csv", cfg, report_path="/tmp/p1_rec_vr.json")["accounts"]}
    rec = {n: recommend(a, assess(a, cfg), cfg) for n, a in accts.items()}

    # BETA — sharp WoW decline → URGENT + book-a-call action with a calendar link
    b = rec["BETA"]
    check("BETA urgency URGENT", b["urgency"] == "URGENT")
    check("BETA WoW below alert", b["wow"] is not None and b["wow"] <= cfg.thresholds.wow_alert)
    check("BETA action is book-a-call", b["action_text"].startswith("Book a call with Sam Ortiz"))
    check("BETA has a calendar link", b["action_link"].startswith("https://calendar.google.com"))
    check("BETA names a driver", "driver" in b["recommendation"].lower())

    # GAMMA — MoM decline (WoW fine) → ELEVATED review, no urgent call
    g = rec["GAMMA"]
    check("GAMMA urgency ELEVATED", g["urgency"] == "ELEVATED")
    check("GAMMA MoM below alert", g["mom"] is not None and g["mom"] <= cfg.thresholds.mom_alert)
    check("GAMMA WoW above alert", g["wow"] is not None and g["wow"] > cfg.thresholds.wow_alert)
    check("GAMMA action is CS review", "review" in g["action_text"].lower())

    # DELTA — no weekly feed → OK + guidance, cadence None
    d = rec["DELTA"]
    check("DELTA no weekly data → wow None", d["wow"] is None)
    check("DELTA guidance to connect a feed", "weekly" in d["recommendation"].lower())

    # ACME — stable → OK
    check("ACME OK", rec["ACME"]["urgency"] == "OK")

    # Ordering: most urgent first
    ordered = recommendations(list(accts.values()), {n: assess(a, cfg) for n, a in accts.items()}, cfg)
    check("BETA sorted first (most urgent)", ordered[0]["account_name"] == "BETA")

    print(f"\n{passed}/{passed + failed} passed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
