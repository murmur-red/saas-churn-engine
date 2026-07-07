"""Local dashboard for Product 1 — deterministic subscription churn. Run:
    streamlit run app.py --server.port 8533

The sidebar lets you PICK which churn signals feed the calculation; the report recomputes over your
selection (deselected/absent signals drop out and lower coverage).
"""
from __future__ import annotations

import json
import sqlite3

import pandas as pd
import streamlit as st

from config import SaasConfig
from adapter import load
from churn import assess
from kpis import portfolio_kpis
from recommendations import recommendations
from signals import REGISTRY, CATEGORIES
from connectors.sql import SQLConnector
from mapping import FieldMapping
from enrichment import enrich, static_provider
from schema_mapper import suggest_mapping

URGENCY_ICON = {"URGENT": "🚨", "ELEVATED": "🟠", "STRATEGIC": "🔵", "OK": "🟢"}

st.set_page_config(page_title="saas-churn-engine", page_icon="📉", layout="wide")
BAND = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢", "UNKNOWN": "⚪"}
CFG = SaasConfig()


@st.cache_data(show_spinner=False)
def _load(csv: str):
    res = load(csv, CFG, report_path="/tmp/p1_validation_report.json")
    return res["accounts"], res["report"]


DEMO_QUERY = "SELECT * FROM crm"
DEMO_MAPPING = {
    "account_name": "customer_name", "booked_arr": "annual_value", "renewal_date": "renews_on",
    "seats_licensed": "licensed_seats", "seats_active_series": "active_seats",
    "feature_adoption_pct": "adoption_rate", "nps_series": "latest_nps", "account_owner": "csm_owner",
}


def _demo_db():
    """An in-memory SQLite CRM (customer's own column names) — stands in for a real warehouse."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE crm(customer_name TEXT, annual_value REAL, renews_on TEXT, "
                 "licensed_seats INT, active_seats INT, adoption_rate REAL, latest_nps REAL, csm_owner TEXT)")
    conn.executemany("INSERT INTO crm VALUES (?,?,?,?,?,?,?,?)", [
        ("BigCo", 500000, "2026-07-15", 100, 40, 0.30, -10, "Dana"),
        ("SmallCo", 120000, "2027-03-01", 50, 47, 0.85, 60, "Sam"),
        ("MidCo", 300000, "2026-09-01", 80, 60, 0.55, 25, "Lee"),
    ])
    conn.commit()
    return conn


st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;800&display=swap');
.stApp { background:
    radial-gradient(1100px 500px at 85% -8%, rgba(225,29,72,.06), transparent 60%),
    radial-gradient(900px 420px at 0% 0%, rgba(153,27,27,.04), transparent 55%), #fbf9f9; }
.mr-badge { font-family:'JetBrains Mono',monospace; font-size:10px; letter-spacing:.28em;
    text-transform:uppercase; color:#b91c1c; background:#fef2f2; border:1px solid #fecaca;
    padding:4px 10px; border-radius:5px; }
.mr-title { font-weight:900; font-size:2.5rem; line-height:1.02; letter-spacing:-.02em; margin:.55rem 0 .35rem;
    background:linear-gradient(90deg,#292524,#b91c1c 60%,#e11d48); -webkit-background-clip:text;
    -webkit-text-fill-color:transparent; }
.mr-sub { color:#57534e; font-size:.95rem; font-weight:400; max-width:52rem; }
.mr-flow { font-family:'JetBrains Mono',monospace; font-size:11px; letter-spacing:.06em; color:#78716c; margin-top:.4rem; }
.mr-flow b { color:#b91c1c; font-weight:600; }
.stMarkdown h4, .stMarkdown h3 { font-weight:800 !important; letter-spacing:-.01em; color:#1c1917;
    border-left:3px solid #e11d48; padding-left:.6rem; }
[data-testid="stMetric"] { background:#ffffff; border:1px solid #e7e5e4; border-radius:10px;
    padding:14px 16px; box-shadow:0 1px 2px rgba(28,25,23,.06); }
[data-testid="stMetricLabel"] p { font-family:'JetBrains Mono',monospace; font-size:10px !important;
    letter-spacing:.18em; text-transform:uppercase; color:#78716c !important; }
[data-testid="stMetricValue"] { color:#1c1917; font-weight:800; }
.stButton>button, .stDownloadButton>button { background:#b91c1c; color:#fff; border:1px solid rgba(153,27,27,.25);
    border-radius:7px; font-weight:600; letter-spacing:.02em; transition:all .15s; }
.stButton>button:hover, .stDownloadButton>button:hover { background:#dc2626; transform:translateY(-1px);
    box-shadow:0 6px 18px rgba(190,18,60,.25); }
[data-testid="stExpander"] { background:#ffffff; border:1px solid #e7e5e4; border-radius:10px; }
[data-testid="stExpander"] summary:hover { color:#b91c1c; }
div[data-testid="stNotification"] { border-radius:9px; border:1px solid #e7e5e4; }
[data-testid="stSidebar"] { background:#faf7f7; border-right:1px solid #eee7e5; }
hr { border-color:#e7e5e4 !important; }
.stCaption, .stCaption p { color:#78716c; }
.mr-nav { display:flex; align-items:center; justify-content:space-between;
    border-bottom:1px solid #e7e5e4; padding:0 2px 12px; margin-bottom:18px; }
.mr-wm { font-weight:900; font-size:1.05rem; letter-spacing:-.02em;
    background:linear-gradient(90deg,#292524,#b91c1c,#e11d48); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }
.mr-navbadge { font-family:'JetBrains Mono',monospace; font-size:9px; letter-spacing:.22em; text-transform:uppercase;
    color:#b91c1c; background:#fef2f2; border:1px solid #fecaca; padding:3px 8px; border-radius:5px; margin-left:10px; }
.mr-nav-r a { font-family:'JetBrains Mono',monospace; font-size:11px; letter-spacing:.16em; text-transform:uppercase;
    color:#78716c; text-decoration:none; margin-left:22px; transition:color .15s; }
.mr-nav-r a:hover { color:#b91c1c; }
</style>
<div class="mr-nav">
  <div><span class="mr-wm">murmur.red</span><span class="mr-navbadge">🌐 Portfolio · Churn Engine</span></div>
  <div class="mr-nav-r">
    <a href="#methodology">Methodology</a>
    <a href="https://spend.murmur.red" target="_blank">Spend Control ↗</a>
    <a href="https://github.com/murmur-red/saas-churn-engine" target="_blank">GitHub</a>
  </div>
</div>
<div>
  <span class="mr-badge">📉 murmur.red · churn telemetry</span>
  <div class="mr-title">Deterministic Subscription Churn</div>
  <div class="mr-sub">No LLM in the verdict — pick the signals that matter and the risk report recomputes
     over your selection, with an auditable band, score, and coverage on every account.</div>
  <div class="mr-flow">signals → weighted risk → coverage → <b>band + combinatorial escalation</b> → cadence</div>
</div>
""", unsafe_allow_html=True)
st.caption("Band is the authoritative triage verdict; score is a comparable rank; coverage = share of "
           "signal weight actually used.")

st.markdown('<div id="methodology"></div>', unsafe_allow_html=True)   # anchor for the Methodology nav link
with st.expander("📘 Start here — what this is, how to connect your data, and what each metric means", expanded=False):
    st.markdown("""
**What this is.** A deterministic churn engine for subscription SaaS — *no AI black box*. It reads
your customer signals, applies transparent rules, and tells you **which accounts are at risk and why**.

**How to connect your data** (sidebar → *Data source*):
1. **Sample file** — the bundled demo.
2. **Connect a database** — point `SQLConnector` at your warehouse (Snowflake / BigQuery / Postgres /
   Redshift) or CRM export, write one SQL query returning a row per account, and **map your columns to
   ours** once. In production the same interface backs Salesforce / Stripe / Tableau connectors.
3. **CSV** — fill `subscription_accounts.csv` and drop it in.

**What each output means:**
- **Band** (🔴 CRITICAL → 🟢 LOW / ⚪ UNKNOWN) — the *authoritative* triage verdict; what you act on.
- **Risk score (0–100)** — a comparable rank to sort accounts *within* a band. It's a heuristic, **not** a probability.
- **Coverage** — the share of signal *weight* you actually supplied. Low coverage → the account is flagged **low-confidence**.
- **Exposure** — heuristic `risk × booked ARR` (dollars at stake), not a forecast.
- **GRR / NRR / logo churn** — the lagging retention KPIs (need `prior_period_arr` + expansion/contraction/churned).
- **Cadence (WoW / MoM / QoQ)** — a *week-over-week* decline escalates immediately (book a call with the owner); MoM → monthly review; QoQ → strategic. Needs a `weekly_usage_series` + `account_owner`.

**What if you don't track some of these metrics?** *That's expected — nobody has all 30.* Just leave
that column blank or **uncheck the signal** in the sidebar. The engine simply runs over what you have,
**coverage drops**, and the account is marked low-confidence. Missing data is **quarantined as UNKNOWN,
never read as healthy** — so partial data never hides a risk. The more you connect, the higher the confidence.

**Where each signal comes from:** CRM (ARR/renewal/owner/sponsor) · product analytics (seats, logins,
adoption, retention) · support (tickets/CSAT) · billing (payment health) · CS platform (goals, NPS).
Connect the systems you have; the sidebar shows every signal and its weight.
""")

# ── Signal picker ────────────────────────────────────────────────────────────
st.sidebar.markdown("### Signals to include")
st.sidebar.caption(f"Pick which of the {len(REGISTRY)} churn signals feed the calculation.")
enabled: list[str] = []
for cat in CATEGORIES:
    sigs = [s for s in REGISTRY if s.category == cat]
    with st.sidebar.expander(f"{cat} ({len(sigs)})", expanded=(cat == "Engagement")):
        for s in sigs:
            if st.checkbox(f"{s.label}  ·  w={s.weight:g}", value=True, key=f"sig_{s.key}"):
                enabled.append(s.key)

# ── Data source ──────────────────────────────────────────────────────────────
st.sidebar.markdown("### Data source")
source = st.sidebar.radio("Where does the data come from?", ["Sample file", "Connect a database (demo)"])

if source == "Sample file":
    try:
        accounts, report = _load("subscription_accounts.csv")
    except Exception as e:  # noqa: BLE001
        st.error(f"Could not load data: {e}")
        st.stop()
else:
    st.markdown("#### 🔌 Connect a database — no manual entry")
    st.caption("`SQLConnector` runs against any DB-API connection (Snowflake/Postgres/BigQuery/Redshift "
               "in prod; an in-memory SQLite CRM here). Edit the query + column mapping and fetch — "
               "unmapped columns just lower coverage, never faked.")
    qcol, mcol = st.columns(2)
    query = qcol.text_area("SQL query (returns one row per account)", DEMO_QUERY, height=110)
    if "p1_mapping" not in st.session_state:
        st.session_state["p1_mapping"] = json.dumps(DEMO_MAPPING, indent=2)
    if qcol.button("🪄 Auto-map columns with AI (claude-sonnet-5)"):
        try:
            _rows = SQLConnector(_demo_db(), query).fetch()
            _cols = list(_rows[0].keys()) if _rows else []
            with st.spinner("Asking the model to match your columns to our fields…"):
                sug = suggest_mapping(_cols, sample_rows=_rows)
            st.session_state["p1_mapping"] = json.dumps(sug["mapping"], indent=2)
            qcol.success(f"AI mapped {len(sug['mapping'])} of {len(_cols)} columns — review on the right, then edit if needed.")
        except Exception as e:  # noqa: BLE001
            qcol.error(f"Auto-map failed: {e}")
    qcol.caption("AI *suggests* the mapping (validated to real fields); you review it. The churn engine stays deterministic.")
    mapping_json = mcol.text_area("Field mapping — our_field: their_column", height=200, key="p1_mapping")
    do_enrich = st.checkbox("Enrich company-health gap (3rd-party; first-party data wins)", value=True)
    try:
        mapping = FieldMapping(json.loads(mapping_json), transforms={"seats_active_series": str, "nps_series": str})
        rows = SQLConnector(_demo_db(), query).fetch()
        accounts = mapping.apply(rows, constants={"source": "warehouse", "data_as_of": CFG.today})
        report = {"counts": {"accepted": len(accounts), "rejected": 0}}
        with st.expander("Pulled rows (their schema) → mapped (our schema)"):
            st.write("Raw rows from the database:", rows)
            st.write("Mapped into our signal schema (pre-enrichment):", accounts)
        if do_enrich:   # after the expander, so it shows the pure mapping
            enrich(accounts, "external_risk_flag", static_provider({"BigCo": "true"}))
    except json.JSONDecodeError as e:
        st.error(f"Field mapping is not valid JSON: {e}")
        st.stop()
    except Exception as e:  # noqa: BLE001
        st.error(f"Connector / mapping error: {e}")
        st.stop()

if not accounts:
    st.warning("No accounts returned — check the data source, query, and mapping.")
    st.stop()
if not enabled:
    st.warning("No signals selected — pick at least one signal in the sidebar to run the report.")
    st.stop()

verdicts = [assess(a, CFG, enabled) for a in accounts]
kpis = portfolio_kpis(accounts)

st.info(f"Running churn calculation over **{len(enabled)} of {len(REGISTRY)}** signals.")

c1, c2, c3, c4 = st.columns(4)
c1.metric("GRR", f"{kpis['grr']*100:.1f}%" if kpis["grr"] is not None else "N/A")
c2.metric("NRR", f"{kpis['nrr']*100:.1f}%" if kpis["nrr"] is not None else "N/A")
c3.metric("Logo churn", f"{kpis['logo_churn']*100:.1f}%" if kpis["logo_churn"] is not None else "N/A")
c4.metric("Accounts", report["counts"]["accepted"], delta=f"{report['counts']['rejected']} rejected", delta_color="off")

st.divider()
table = pd.DataFrame([{
    "": BAND.get(v["band"], "⚪"),
    "Account": v["account_name"],
    "Segment": v["segment"],
    "Band": v["band"],
    "Escalated": "⤴️" if v["escalated"] else "",
    "Risk": v["risk_score"] if v["risk_score"] is not None else 0,
    "Coverage": v["coverage"],
    "Low conf": "⚠️" if v["low_confidence"] else "",
    "Signals used": len(v["signals_used"]),
    "Exposure": v["risk_weighted_exposure"] if v["risk_weighted_exposure"] is not None else 0,
} for v in sorted(verdicts, key=lambda x: (-(x["risk_score"] or 0), x["account_name"]))])
st.dataframe(table, hide_index=True, use_container_width=True, column_config={
    "Risk": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f"),
    "Coverage": st.column_config.ProgressColumn(min_value=0.0, max_value=1.0, format="%.2f"),
    "Exposure": st.column_config.NumberColumn(format="$%d",
        help="heuristic (risk_score/100 × booked ARR), NOT a calibrated churn probability"),
})

st.divider()
st.markdown("#### 📆 Cadence & recommendations — WoW / MoM / QoQ / ARR")
st.caption("A WoW decline escalates immediately (book a call with the owner); MoM → monthly review; "
           "QoQ → strategic review. The band stays the severity; cadence sets urgency & the action.")
recs = recommendations(accounts, {v["account_name"]: v for v in verdicts}, CFG)
rec_table = pd.DataFrame([{
    "": URGENCY_ICON.get(r["urgency"], "⚪"),
    "Account": r["account_name"],
    "Owner": r["owner"],
    "Urgency": r["urgency"],
    "Band": r["band"],
    "WoW": None if r["wow"] is None else r["wow"] * 100,
    "MoM": None if r["mom"] is None else r["mom"] * 100,
    "QoQ": None if r["qoq"] is None else r["qoq"] * 100,
    "ARR": r["arr"],
    "Recommendation": r["recommendation"],
    "Action": r["action_link"] or None,
} for r in recs])
st.dataframe(rec_table, hide_index=True, use_container_width=True, column_config={
    "WoW": st.column_config.NumberColumn(format="%.1f%%"),
    "MoM": st.column_config.NumberColumn(format="%.1f%%"),
    "QoQ": st.column_config.NumberColumn(format="%.1f%%"),
    "ARR": st.column_config.NumberColumn(format="$%d"),
    "Action": st.column_config.LinkColumn("Action", display_text="📅 book call"),
})
for r in recs:
    if r["urgency"] == "URGENT":
        st.error(f"🚨 {r['account_name']} — {r['recommendation']}  ·  **{r['action_text']}**")

st.divider()
sel = st.selectbox("Inspect account", [v["account_name"] for v in verdicts])
chosen = next((v for v in verdicts if v["account_name"] == sel), None)
if chosen is None:
    st.stop()
st.write(f"**{BAND.get(chosen['band'])} {chosen['band']}** · risk {chosen['risk_score']} · "
         f"coverage {chosen['coverage']} · {len(chosen['signals_used'])} signals used, "
         f"{len(chosen['signals_unavailable'])} unavailable")
fired = [r for r in chosen["reasons"] if r.startswith("[") or r.startswith("escalated")]
if fired:
    st.markdown("**Fired flags**")
    for r in fired:
        st.write(f"- {r}")
else:
    st.caption("No risk flags fired for the selected signals.")
