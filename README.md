# saas-churn-engine — deterministic subscription-SaaS churn (Product 1)

A standalone, **deterministic** churn engine for subscription SaaS. No LLM, no usage/token concepts.
A transparent rule-tree verdict over subscription leading indicators, a fixed-weight risk rank with
coverage, and portfolio GRR/NRR/logo churn. Pure-Python standard library only.

## Layout (self-contained)
| File | Role |
|---|---|
| `config.py` | `SaasConfig` + `SaasThresholds` — every threshold/weight named & tunable. |
| `adapter.py` | Ingest gate: schema/range validation, hard-reject vs warn, stale-data hard-fail (default), data contract (`source`/`data_as_of`/freshness SLA) + `validation_report.json` audit. |
| `churn.py` | Verdict engine: rule tree + combinatorial escalation; fixed-weight risk score + coverage (missing factor → 0, not renormalized); band authoritative, score secondary; missing inputs quarantined as `UNKNOWN`. |
| `kpis.py` | Portfolio GRR / NRR / logo churn with zero-cohort guard. |
| `core/` | Vendored numeric primitives — `series.py` (mom/qoq/run_rate/variance), `scoring.py` (expected_value, band). Domain-agnostic; kept in sync with `ai-spend-control`'s copy. |
| `subscription_accounts.csv` | Synthetic dataset exercising healthy / critical / escalation / insufficient-history / seat-overcount. |

## Run
```bash
python test_characterization.py    # pins engine outputs (42 assertions)
python test_boundary.py            # enforces token/AI/LLM-free (41 assertions)
```

## Notes
- `core/` is a **vendored copy** (each product is fully standalone). If you change a core primitive,
  mirror it into `ai-spend-control/core/`.
- Verdict band is the authoritative triage signal; `risk_score` is a secondary comparable rank.
  `risk_weighted_exposure` is a heuristic, **not** a calibrated churn probability/forecast.
