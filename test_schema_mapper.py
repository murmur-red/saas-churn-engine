#!/usr/bin/env python3
"""
Tests for the AI schema mapper. The LLM is injected (mocked) so the target catalog and the grounding
critic are tested deterministically — including dropping a hallucinated target and a bad source. An
optional live smoke runs only when RUN_LIVE_MAPPER=1. Run: python test_schema_mapper.py
"""
from __future__ import annotations

import os
import sys

from schema_mapper import suggest_mapping, target_fields

passed = failed = 0


def check(label, cond):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"  FAIL  {label}")


COLUMNS = ["customer_name", "annual_value", "renews_on", "licensed_seats", "active_seats",
           "adoption_rate", "latest_nps", "csm_owner"]


def _mock(prompt, model):
    import json
    return json.dumps({"mapping": {
        "account_name": "customer_name",           # valid
        "booked_arr": "annual_value",              # valid
        "feature_adoption_pct": "adoption_rate",   # valid
        "seats_licensed": "licensed_seats",        # valid
        "account_owner": "csm_owner",              # valid
        "not_a_real_field": "latest_nps",          # hallucinated TARGET → must drop
        "nps_series": "does_not_exist",            # bad SOURCE → must drop
    }})


def main() -> None:
    check("target catalog includes core + signals", {"account_name", "feature_adoption_pct"} <= set(target_fields()))

    res = suggest_mapping(COLUMNS, sample_rows=[{"customer_name": "BigCo", "annual_value": 500000}], llm=_mock)
    m = res["mapping"]
    check("valid mapping kept (account_name)", m.get("account_name") == "customer_name")
    check("valid mapping kept (booked_arr)", m.get("booked_arr") == "annual_value")
    check("hallucinated target dropped", "not_a_real_field" not in m)
    check("bad source dropped", "nps_series" not in m)
    check("unmapped source reported", "latest_nps" in res["unmapped_sources"])

    # one source can't feed two targets
    def _dup(prompt, model):
        import json
        return json.dumps({"mapping": {"account_name": "customer_name", "segment": "customer_name"}})
    dm = suggest_mapping(COLUMNS, llm=_dup)["mapping"]
    check("a source maps to at most one target", list(dm.values()).count("customer_name") == 1)

    # Optional live smoke
    if os.getenv("RUN_LIVE_MAPPER") == "1" and os.getenv("ANTHROPIC_API_KEY"):
        live = suggest_mapping(COLUMNS)["mapping"]
        check("live: account_name ← customer_name", live.get("account_name") == "customer_name")
        check("live: booked_arr ← annual_value", live.get("booked_arr") == "annual_value")

    print(f"\n{passed}/{passed + failed} passed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
