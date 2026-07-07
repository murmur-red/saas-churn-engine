# 📉 saas-churn-engine

**Deterministic churn detection for subscription SaaS — no LLM in the verdict.**

![python](https://img.shields.io/badge/python-3.11%2B-blue)
![streamlit](https://img.shields.io/badge/UI-Streamlit-e11d48)
![verdict](https://img.shields.io/badge/verdict-deterministic%20·%20LLM--free-111)
![tests](https://img.shields.io/badge/tests-108%20passing-brightgreen)

Most churn tools hand you a black-box "risk score" you can't audit. This does the opposite: a
**transparent, rule-based verdict** over the leading indicators of subscription churn — every number
traceable to a signal you chose, with **no model you have to trust**. The churn math is pure standard
library; AI is used only to help you *onboard* your data, never to decide the verdict.

> Part of the **murmur.red** portfolio · sibling project → [**ai-spend-control**](https://github.com/murmur-red/ai-spend-control) (the buy-side of the same coin).

---

## What it does

- **Signal registry (~30 selectable signals)** across engagement, adoption, support, and commercial
  health — you pick which ones count, and the report recomputes over your selection.
- **Fixed-weight risk score + coverage** — a missing signal *lowers coverage*; it is never silently
  reweighted or faked.
- **Authoritative band** (`CRITICAL … LOW`) with **combinatorial escalation** (two mediums escalate)
  and a **renewal amplifier**; `UNKNOWN` accounts are quarantined, not guessed.
- **Portfolio KPIs** — GRR / NRR / logo churn with a zero-cohort guard.
- **Cadence & recommendations** — WoW / MoM / QoQ / ARR movement, each with a next action (book a
  call, monthly review, strategic review).
- **Onboarding without manual entry** — Salesforce / Stripe / SQL connectors + an **AI-assisted schema
  mapper** that maps *their* columns to ours (isolated from the scoring engine).
- **Streamlit dashboard** in the murmur.red theme.

## Why it's interesting (design notes)

- **Deterministic by construction.** The verdict engine is LLM-free and stdlib-only — enforced by a
  **boundary test (41 assertions)** that *fails the build* if any token/AI/LLM concept leaks into it.
- **Coverage, not renormalization.** Absent data reduces confidence transparently instead of quietly
  redistributing weight to whatever signals happen to be present.
- **AI only at the edge.** The optional schema-mapper uses an LLM to speed up onboarding, then a
  deterministic critic keeps only real target fields — so nothing an LLM says can move a risk score.
- **Vendored `core/`.** Numeric primitives are copied into each product (fully standalone folders) and
  guarded by a parity test against the sibling repo.

## Quickstart

```bash
pip install -r requirements.txt

streamlit run app.py            # launch the dashboard

# tests — 108 assertions, no network, engine is pure standard library
python test_characterization.py # pins engine outputs
python test_boundary.py         # proves the verdict stays token/AI/LLM-free
```

## Layout

| File | Role |
|---|---|
| `app.py` | Streamlit dashboard — signal picker, risk table, cadence, connect-a-database panel. |
| `signals.py` | The signal **registry** — ~30 `Signal(kind, field, params)` definitions + `evaluate()`. |
| `churn.py` | Verdict engine: fixed-weight score + coverage, band + escalation + renewal amplifier. |
| `kpis.py` | Portfolio GRR / NRR / logo churn. |
| `recommendations.py` | Cadence (WoW/MoM/QoQ/ARR) → prioritized next actions. |
| `adapter.py` | Ingest gate: schema/range validation, hard-reject vs warn, stale-data hard-fail, audit report. |
| `connectors/` | Dependency-injected Salesforce / Stripe / SQL connectors + field mapping + enrichment. |
| `schema_mapper.py` | AI-assisted onboarding mapper (isolated from the deterministic engine). |
| `core/` | Vendored numeric primitives (parity-guarded against `ai-spend-control/core`). |

## Status

A **prototype on synthetic data**, built to demonstrate the architecture. `risk_weighted_exposure` is a
heuristic exposure figure — **not** a calibrated churn probability or forecast. The band is the
authoritative triage signal; `risk_score` is a secondary comparable rank.

---

<sub>Built with Claude Code. Sibling: [ai-spend-control](https://github.com/murmur-red/ai-spend-control).</sub>
