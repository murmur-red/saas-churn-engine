"""Cadence-driven recommendations for Product 1.

For each account: compute WoW / MoM / QoQ (+ ARR level) from its weekly usage series, then apply
deterministic escalation:
  • WoW decline ≤ wow_alert  → URGENT: escalate now, name the likely driver, and produce a
    "book a call with {owner}" action (a pre-filled calendar link).
  • MoM decline ≤ mom_alert  → ELEVATED: monthly review + intervention plan.
  • QoQ decline ≤ qoq_alert  → STRATEGIC: schedule an executive business review.
  • else, if the churn band is HIGH/CRITICAL → proactive check-in (signals elevated even if usage flat).
  • else → OK / monitor.
The band (from churn.assess) stays the authoritative severity; cadence sets the *urgency & action*.
"""
from __future__ import annotations

import urllib.parse
from typing import Any, Optional

from core.cadence import cadence

URGENCY_RANK = {"OK": 0, "STRATEGIC": 1, "ELEVATED": 2, "URGENT": 3}


def _weekly(account: dict) -> Optional[list[float]]:
    v = account.get("weekly_usage_series")
    if not v:
        return None
    try:
        s = [float(x) for x in str(v).split(";") if x.strip() != ""]
        return s or None
    except ValueError:
        return None


def _driver(verdict: dict) -> str:
    fired = [r for r in verdict.get("reasons", []) if r.startswith("[")]
    if fired:
        return fired[0].split("] ", 1)[-1]          # strip the [TIER] prefix
    return f"churn band {verdict.get('band', '?')}"


def _calendar_link(account: str, owner: str, why: str) -> str:
    text = urllib.parse.quote(f"Churn escalation: {account}")
    details = urllib.parse.quote(f"Owner: {owner}\nWhy: {why}")
    return f"https://calendar.google.com/calendar/render?action=TEMPLATE&text={text}&details={details}"


def recommend(account: dict[str, Any], verdict: dict[str, Any], config) -> dict[str, Any]:
    t = config.thresholds
    owner = account.get("account_owner") or "(unassigned)"
    name = account.get("account_name", "?")
    band = verdict.get("band", "UNKNOWN")
    driver = _driver(verdict)

    weekly = _weekly(account)
    c = cadence(weekly) if weekly else {"wow": None, "mom": None, "qoq": None, "yoy": None}

    def pct(x): return f"{x*100:+.1f}%" if x is not None else "n/a"

    urgency, rec, action_text, action_link = "OK", "Stable — monitor.", "", ""

    if c["wow"] is not None and c["wow"] <= t.wow_alert:
        urgency = "URGENT"
        rec = f"WoW {pct(c['wow'])}. Likely driver: {driver}. Escalate immediately."
        action_text = f"Book a call with {owner}"
        action_link = _calendar_link(name, owner, f"WoW {pct(c['wow'])} — {driver}")
    elif c["mom"] is not None and c["mom"] <= t.mom_alert:
        urgency = "ELEVATED"
        rec = f"MoM {pct(c['mom'])}. Driver: {driver}. Add to this week's CS review and plan intervention."
        action_text = f"Add {name} to CS review"
    elif c["qoq"] is not None and c["qoq"] <= t.qoq_alert:
        urgency = "STRATEGIC"
        rec = f"QoQ {pct(c['qoq'])}. Schedule an executive business review with {owner}."
        action_text = "Schedule EBR"
    elif band in ("HIGH", "CRITICAL"):
        urgency = "ELEVATED"
        rec = f"Usage steady but churn signals {band}: {driver}. Proactive check-in."
        action_text = f"Proactive check-in ({owner})"

    # No weekly feed: append the guidance (never overwrite a band-driven recommendation).
    if weekly is None:
        note = "No weekly usage feed — connect one to enable week-over-week escalation."
        rec = note if (urgency == "OK" and not action_text) else f"{rec} ({note})"

    return {
        "account_name": name, "owner": owner, "band": band,
        "wow": c["wow"], "mom": c["mom"], "qoq": c["qoq"],
        "arr": round(float(account.get("booked_arr", 0) or 0)),
        "urgency": urgency, "recommendation": rec,
        "action_text": action_text, "action_link": action_link,
    }


def recommendations(accounts: list[dict], verdicts_by_name: dict[str, dict], config) -> list[dict]:
    """Recommendation rows, most-urgent first (then largest WoW decline, then name)."""
    rows = [recommend(a, verdicts_by_name.get(a.get("account_name"), {}), config) for a in accounts]
    # Within an urgency band: most-declining WoW first; no-data (None) sorts LAST (not as 0.0).
    return sorted(rows, key=lambda r: (-URGENCY_RANK.get(r["urgency"], 0),
                                       r["wow"] if r["wow"] is not None else float("inf"),
                                       r["account_name"]))
