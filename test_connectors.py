#!/usr/bin/env python3
"""
End-to-end connector test: pull from a (SQLite) customer database → map their columns to our signal
schema → enrich a gap → run the churn engine. Proves "connect a DB, get real results" with zero manual
entry and no external credentials. The same SQLConnector works on Postgres/Snowflake/BigQuery in prod.
Run: python test_connectors.py
"""
from __future__ import annotations

import sqlite3
import sys

from config import SaasConfig
from connectors.sql import SQLConnector
from mapping import FieldMapping
from enrichment import enrich, static_provider
from churn import assess
from kpis import portfolio_kpis

passed = failed = 0


def check(label, cond):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"  FAIL  {label}")


def _customer_db():
    """A DB with the customer's OWN column names (not ours)."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE crm(customer_name TEXT, annual_value REAL, renews_on TEXT, "
                 "licensed_seats INT, active_seats INT, adoption_rate REAL, latest_nps REAL, csm_owner TEXT)")
    conn.executemany("INSERT INTO crm VALUES (?,?,?,?,?,?,?,?)", [
        ("BigCo", 500000, "2026-07-15", 100, 40, 0.30, -10, "Dana"),   # low util + adoption + negative NPS, renews soon
        ("SmallCo", 120000, "2027-03-01", 50, 47, 0.85, 60, "Sam"),    # healthy
    ])
    conn.commit()
    return conn


MAPPING = FieldMapping(
    mapping={
        "account_name": "customer_name",
        "booked_arr": "annual_value",
        "renewal_date": "renews_on",
        "seats_licensed": "licensed_seats",
        "seats_active_series": "active_seats",
        "feature_adoption_pct": "adoption_rate",
        "nps_series": "latest_nps",
        "account_owner": "csm_owner",
    },
    transforms={"seats_active_series": str, "nps_series": str},   # single point → series-parseable
)


def main() -> None:
    cfg = SaasConfig()
    conn = _customer_db()

    # ── 1. Pull from the customer DB (their schema) ─────────────────────────
    rows = SQLConnector(conn, "SELECT * FROM crm").fetch()
    check("connector pulled 2 rows", len(rows) == 2)
    check("rows carry the customer's column names", "annual_value" in rows[0] and "customer_name" in rows[0])

    # ── 2. Map their columns → our signal schema ────────────────────────────
    accts = MAPPING.apply(rows, constants={"source": "warehouse", "data_as_of": cfg.today})
    by = {a["account_name"]: a for a in accts}
    check("mapped into our schema", by["BigCo"]["booked_arr"] == 500000)

    # ── 3. Real churn verdicts from DB-pulled data ──────────────────────────
    vb, vs = assess(by["BigCo"], cfg), assess(by["SmallCo"], cfg)
    check("BigCo → CRITICAL from pulled data", vb["band"] == "CRITICAL")
    check("SmallCo → LOW from pulled data", vs["band"] == "LOW")
    check("coverage < 1 (only mapped signals available)", vb["coverage"] < 1.0)
    check("low confidence flagged (partial connect)", vb["low_confidence"] is True)
    check("unmapped signal is unavailable, not faked", "payment_health" in vb["signals_unavailable"])
    check("portfolio KPIs tolerate missing movement fields (no crash → N/A)",
          portfolio_kpis(accts)["grr"] is None)

    # ── 4. Enrichment fills a known gap (company-health), first-party wins ──
    summary = enrich(accts, "external_risk_flag", static_provider({"BigCo": "true"}))
    check("enrichment filled 1 gap", summary["filled"] == 1)
    vb2 = assess(by["BigCo"], cfg)
    check("enriched signal now contributes", "external_risk" in vb2["signals_used"])
    check("enrichment recorded for audit", "external_risk_flag" in by["BigCo"].get("_enriched", []))

    # ── Ambiguous mapping is rejected ───────────────────────────────────────
    try:
        FieldMapping({"account_name": "x", "booked_arr": "x"})
        check("ambiguous mapping rejected", False)
    except ValueError:
        check("ambiguous mapping rejected", True)

    print(f"\n{passed}/{passed + failed} passed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
