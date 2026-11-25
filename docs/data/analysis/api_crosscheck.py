"""
Cross-check for CHURN-9, CHURN-10 and CHURN-11: compares the independent
figures in results/e1_results.json, and the CHURN-11 recomputation in
docs/analytics/results/recomputed_values.json, with what the API returns.

The API is called in-process through FastAPI's TestClient, so no server or
network is needed. Run from the repository root:
    python docs/data/analysis/api_crosscheck.py

Writes docs/data/analysis/results/api_crosscheck.json and exits non-zero if
any compared value differs.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RESULTS = Path(__file__).resolve().parent / "results"
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")
os.environ.pop("GEMINI_API_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402

client = TestClient(main.app)
seg_api = client.get("/segments").json()
dash_api = client.get("/dashboard/summary").json()
e1 = json.loads((RESULTS / "e1_results.json").read_text())["churn9_segments"]
aryan = json.loads((ROOT / "docs/analytics/results/recomputed_values.json").read_text())

mismatches: list[str] = []
segments_out = {}
API_KEYS = {"plan_type": "by_plan", "device_type": "by_device",
            "tenure_bucket": "by_tenure", "preferred_genre": "by_genre"}
for col, api_field in API_KEYS.items():
    api_rows = {str(r[col]): r for r in seg_api[api_field]}
    rows = []
    for r in e1["one_way"][col]["rows"]:
        a = api_rows.get(r["group"])
        ok = a is not None and a["count"] == r["n"] and abs(a["churn_rate_pct"] - r["mean_predicted_pct"]) < 0.05
        if not ok:
            mismatches.append(f"/segments {api_field} {r['group']}")
        rows.append({"group": r["group"], "n_independent": r["n"], "n_api": a and a["count"],
                     "mean_predicted_independent": r["mean_predicted_pct"],
                     "churn_rate_pct_api": a and a["churn_rate_pct"],
                     "observed_churn_independent": r["observed_churn_pct"],
                     "gap_observed_minus_predicted": round(r["observed_churn_pct"] - r["mean_predicted_pct"], 1),
                     "match": ok})
    segments_out[api_field] = rows
if abs(seg_api["overall"]["avg_churn_rate_pct"] - e1["overall_mean_predicted_pct"]) >= 0.05:
    mismatches.append("/segments overall avg_churn_rate_pct")

# CHURN-11: does the merged recomputation still agree with the API on today's main?
k = dash_api["kpis"]
dash_checks = {}


def check(name, api_value, recomputed):
    ok = api_value == recomputed if not isinstance(recomputed, float) else abs(api_value - recomputed) < 0.01
    dash_checks[name] = {"api": api_value, "recomputed": recomputed, "match": ok}
    if not ok:
        mismatches.append(f"/dashboard/summary {name}")


rd = aryan["dashboard"]
risk = rd["risk_counts_from_probability"]
sig = rd["churn_signals"]
check("total_customers", k["total_customers"], sum(risk.values()))
check("high_risk_count", k["high_risk_count"], risk["HIGH"])
check("medium_risk_count", k["medium_risk_count"], risk["MEDIUM"])
check("low_risk_count", k["low_risk_count"], risk["LOW"])
check("high_risk_pct", k["high_risk_pct"], float(rd["high_risk_pct"]))
check("avg_churn_probability", k["avg_churn_probability"], float(rd["avg_churn_prob"]))
check("revenue_at_risk_monthly", k["revenue_at_risk_monthly"], float(rd["revenue_at_risk_monthly"]))
check("high_value_at_risk", k["high_value_at_risk"], rd["high_risk_and_high_model_clv"])
crb = dash_api["churn_reasons_breakdown"]
check("signal_low_engagement", crb["low_engagement"], sig["low_engagement_watch_lt_3h"])
check("signal_payment_issues", crb["payment_issues"], sig["payment_issues_failures_gt_0"])
check("signal_new_customers", crb["new_customers"], sig["new_customers_tenure_lt_6m"])
check("signal_support_issues", crb["support_issues"], sig["support_issues_tickets_gt_1"])
clv_api = {r["clv_segment"]: r["count"] for r in seg_api["by_clv"]}
for tier, n in rd["model_clv_tiers"].items():
    check(f"clv_tier_{tier}", clv_api.get(tier), n)

out = {"segments": segments_out,
       "segments_overall": {"api": seg_api["overall"], "independent_mean_predicted_pct": e1["overall_mean_predicted_pct"],
                            "independent_observed_pct": e1["overall_observed_pct"]},
       "dashboard_vs_recomputed_values_json": dash_checks,
       "dashboard_api_kpis": k,
       "mismatches": mismatches}
(RESULTS / "api_crosscheck.json").write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
print(f"compared {sum(len(v) for v in segments_out.values())} segment rows and {len(dash_checks)} KPIs; "
      f"mismatches: {mismatches or 'none'}")
sys.exit(1 if mismatches else 0)
