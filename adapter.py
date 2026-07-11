"""SubscriptionAdapter — the tolerant ingest gate for Product 1.

Keeps EVERY column as raw data so the signal registry (signals.py) can read whatever the customer
supplies — any subset of the ~30 churn signals. Only a small CORE is validated/coerced (identity +
booked ARR + the renewal-movement fields used by GRR/NRR/logo). Hard-fails on stale data (unless
allowed), rejects bad rows individually (never aborts the file for one bad row), enforces unique
account names, and writes an audit report. Signals coerce their own fields (blank/missing → the
signal is simply unavailable, lowering coverage).
"""
from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

REQUIRED_COLUMNS = {"account_name", "booked_arr", "source", "data_as_of"}
MOVEMENT_FIELDS = ("prior_period_arr", "expansion_arr", "contraction_arr", "churned_arr")


class SchemaError(RuntimeError):
    pass


class StaleDataError(RuntimeError):
    pass


def load(csv_path: str, config, report_path: str | None = None) -> dict[str, Any]:
    path = Path(csv_path)
    if not path.exists():
        raise SchemaError(f"data file not found: {csv_path}")
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        cols = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS - cols
        if missing:
            raise SchemaError(f"missing required columns: {sorted(missing)}")
        rows = [{k: (v.strip() if isinstance(v, str) else v) for k, v in r.items()} for r in reader]
    if not rows:
        raise SchemaError("no data rows")

    source = rows[0]["source"]
    data_as_of = rows[0]["data_as_of"]
    if any(r["source"] != source or r["data_as_of"] != data_as_of for r in rows):
        raise SchemaError("inconsistent source/data_as_of across rows")
    age = (datetime.strptime(config.today, "%Y-%m-%d") - datetime.strptime(data_as_of, "%Y-%m-%d")).days
    stale = age > config.max_data_age_days
    if stale and not config.allow_stale:
        raise StaleDataError(f"data {age}d old > {config.max_data_age_days}d SLA; set allow_stale to override")

    accounts, rejected, seen = [], [], set()
    for i, r in enumerate(rows, start=2):
        try:
            name = r["account_name"]
            if not name:
                raise ValueError("empty account_name")
            if name in seen:
                raise ValueError(f"duplicate account_name {name}")
            booked = float(r["booked_arr"])
            if booked < 0:
                raise ValueError("booked_arr < 0")
            r["booked_arr"] = booked
            for m in MOVEMENT_FIELDS:                      # coerce KPI fields (blank → 0.0)
                val = r.get(m, "")
                r[m] = float(val) if val not in ("", None) else 0.0
                if r[m] < 0:
                    raise ValueError(f"{m} < 0")
            seen.add(name)
            accounts.append(r)   # all other columns kept raw for the signals to coerce
        except (ValueError, KeyError) as e:
            rejected.append({"row": str(i), "account": r.get("account_name", "?"), "reason": str(e)})

    report = {
        "source": source, "data_as_of": data_as_of,
        "freshness": {"age_days": age, "stale": stale, "sla_days": config.max_data_age_days},
        "counts": {"accepted": len(accounts), "rejected": len(rejected), "warned": 0},
        "rejected": rejected,
    }
    # Privacy: only persist the report when a caller explicitly asks (e.g. CLI/tests). The app passes
    # report_path=None so uploaded customer data stays in memory and is never written to disk.
    if report_path is not None:
        Path(report_path).write_text(json.dumps(report, indent=2))
    return {"accounts": accounts, "report": report}
