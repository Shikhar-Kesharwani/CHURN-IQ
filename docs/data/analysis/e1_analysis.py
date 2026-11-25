"""
E1 data analysis for CHURN-7 (data quality), CHURN-8 (behaviour) and CHURN-9
(segment patterns).

This script is deliberately independent of the API: it reads the two CSV files
with pandas and does not import backend/main.py or churniq_core. Its numbers
can therefore be used to check the API, not just to repeat it.

Run from the repository root:
    python docs/data/analysis/e1_analysis.py

Writes:
    docs/data/analysis/results/e1_results.json   every number quoted in the docs
    docs/data/figures/*.png                       charts for CHURN-8 and CHURN-9
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
DATASET = ROOT / "backend" / "ott_churn_dataset.csv"
PREDICTIONS = ROOT / "backend" / "customer_predictions.csv"
OUT_JSON = Path(__file__).resolve().parent / "results" / "e1_results.json"
FIG_DIR = ROOT / "docs" / "data" / "figures"

# Domains the generator promises (churniq_ml_pipeline.generate_dataset and
# add_emails.py). A value outside these is a data-quality defect.
NUMERIC_RANGES = {
    "age": (18, 65),
    "monthly_charge": (199, 799),
    "tenure_months": (1, 72),
    "watch_hours_per_week": (0.5, 40.0),
    "num_profiles": (1, 5),
    "logins_last_30_days": (0, 60),
    "last_login_days_ago": (0, 90),
    "payment_failures_3m": (0, 4),
    "support_tickets": (0, 5),
    "churn_probability": (0.0, 1.0),
    "clv_score": (0.0, math.inf),
}
INTEGER_COLS = ["age", "monthly_charge", "tenure_months", "num_profiles",
                "logins_last_30_days", "last_login_days_ago",
                "payment_failures_3m", "support_tickets", "churn"]
CATEGORIES = {
    "gender": {"Male", "Female", "Other"},
    "country": {"India", "UAE", "USA", "UK", "Singapore", "Canada"},
    "plan_type": {"Basic", "Standard", "Premium"},
    "preferred_genre": {"Action", "Drama", "Comedy", "Thriller", "Kids",
                        "Documentary", "Romance"},
    "device_type": {"Mobile", "Laptop", "Smart TV", "Tablet"},
    "payment_method": {"UPI", "Credit Card", "Debit Card", "Wallet"},
    "clv_segment": {"High", "Medium", "Low"},
}
PLAN_PRICE = {"Basic": 199, "Standard": 499, "Premium": 799}
ID_RE = re.compile(r"^CUST\d{5}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Tenure bins used by GET /segments (pd.cut, right-closed), so the observed
# and predicted rates are compared on exactly the same groups.
API_TENURE_BINS = [0, 3, 6, 12, 24, 72]
API_TENURE_LABELS = ["0-3m", "3-6m", "6-12m", "1-2yr", "2yr+"]

MIN_N = 50  # smallest group reported as a "high-risk segment"


def git_blob(path: Path) -> str:
    out = subprocess.run(["git", "hash-object", str(path)], capture_output=True,
                         text=True, check=True, cwd=ROOT)
    return out.stdout.strip()


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion (robust for small n)."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (round(100 * (centre - half), 1), round(100 * (centre + half), 1))


def rate_table(df: pd.DataFrame, by: str, extra_pred: bool = False) -> list[dict]:
    rows = []
    for key, g in df.groupby(by, observed=True, sort=True):
        n, k = len(g), int(g["churn"].sum())
        lo, hi = wilson(k, n)
        row = {"group": str(key), "n": n, "churned": k,
               "observed_churn_pct": round(100 * k / n, 1),
               "ci95_pct": [lo, hi]}
        if extra_pred:
            row["mean_predicted_pct"] = round(100 * g["churn_prob"].mean(), 1)
        rows.append(row)
    return rows


def auc(score: pd.Series, y: pd.Series) -> float:
    """Rank-based ROC-AUC of one variable against churn (0.5 = no signal).
    Uses average ranks, so ties are handled correctly."""
    r = score.rank(method="average")
    n1, n0 = int(y.sum()), int((1 - y).sum())
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def cramers_v(x: pd.Series, y: pd.Series) -> float:
    ct = pd.crosstab(x, y).to_numpy().astype(float)
    n = ct.sum()
    exp = ct.sum(1, keepdims=True) * ct.sum(0, keepdims=True) / n
    chi2 = ((ct - exp) ** 2 / exp).sum()
    k = min(ct.shape) - 1
    return float(math.sqrt(chi2 / (n * k))) if k > 0 else 0.0


# --------------------------------------------------------------------------
# CHURN-7: data quality
# --------------------------------------------------------------------------
def quality(df: pd.DataFrame) -> dict:
    q: dict = {"shape": list(df.shape), "columns": list(df.columns)}
    q["missing_per_column"] = {c: int(v) for c, v in df.isna().sum().items()}
    q["missing_total"] = int(df.isna().sum().sum())
    q["blank_string_cells"] = int(sum(
        (df[c].astype(str).str.strip() == "").sum()
        for c in df.select_dtypes(include="object")))
    q["duplicate_rows"] = int(df.duplicated().sum())
    q["duplicate_rows_ignoring_id"] = int(df.drop(columns=["customer_id"]).duplicated().sum())
    q["duplicate_customer_id"] = int(df["customer_id"].duplicated().sum())
    q["duplicate_customer_id_case_space_insensitive"] = int(
        df["customer_id"].str.strip().str.upper().duplicated().sum())
    q["customer_id_bad_format"] = sorted(df.loc[~df["customer_id"].str.match(ID_RE), "customer_id"].tolist())

    ranges = {}
    for col, (lo, hi) in NUMERIC_RANGES.items():
        s = df[col]
        bad = s[(s < lo) | (s > hi)]
        ranges[col] = {"allowed": [lo, hi if hi != math.inf else None],
                       "observed": [float(s.min()), float(s.max())],
                       "out_of_range": int(len(bad))}
    q["numeric_ranges"] = ranges
    q["non_integer_values"] = {c: int((df[c] != df[c].round()).sum()) for c in INTEGER_COLS}
    q["watch_hours_more_than_1dp"] = int((df["watch_hours_per_week"].round(1) != df["watch_hours_per_week"]).sum())

    cats = {}
    for col, allowed in CATEGORIES.items():
        vals = df[col]
        unknown = sorted(set(vals.unique()) - allowed)
        cats[col] = {"allowed": sorted(allowed),
                     "counts": {k: int(v) for k, v in vals.value_counts().items()},
                     "unknown_values": unknown,
                     "leading_trailing_space": int((vals != vals.str.strip()).sum())}
    q["categories"] = cats

    q["plan_price_mismatch"] = int((df["monthly_charge"] != df["plan_type"].map(PLAN_PRICE)).sum())
    q["churn_label_values"] = {str(k): int(v) for k, v in df["churn"].value_counts().items()}
    q["churn_label_non_binary"] = int((~df["churn"].isin([0, 1])).sum())

    # Generator-side consistency: clv_score and clv_segment follow from
    # churn_probability with the documented formula and cut-offs.
    clv = df["monthly_charge"] * df["tenure_months"].clip(lower=6) * (1 - df["churn_probability"])
    gen = df[df["customer_id"] != "CUST99999"]
    clv_g = clv[gen.index]
    q["clv_formula_max_abs_diff_excl_demo"] = round(float((clv_g - gen["clv_score"]).abs().max()), 2)
    seg = np.where(df["clv_score"] > 8000, "High", np.where(df["clv_score"] > 3000, "Medium", "Low"))
    q["clv_segment_mismatch"] = int((seg != df["clv_segment"]).sum())
    q["email_bad_format"] = int((~df["email"].str.match(EMAIL_RE)).sum())
    q["repeated_name"] = int(df["name"].duplicated().sum())
    q["repeated_email"] = int(df["email"].duplicated().sum())

    demo = df[df["customer_id"] == "CUST99999"]
    q["demo_row"] = {
        "present": bool(len(demo)),
        "clv_score": float(demo["clv_score"].iloc[0]) if len(demo) else None,
        "clv_formula_value": round(float(clv[demo.index].iloc[0]), 2) if len(demo) else None,
        "churn_probability": float(demo["churn_probability"].iloc[0]) if len(demo) else None,
        "churn": int(demo["churn"].iloc[0]) if len(demo) else None,
    }

    # Distribution notes (not errors): ranges much narrower than the generator allows.
    q["notes"] = {
        "logins_observed_max_vs_allowed": [int(df["logins_last_30_days"].max()), 60],
        "last_login_observed_max_vs_allowed": [int(df["last_login_days_ago"].max()), 90],
        "age_observed_max_vs_allowed": [int(df["age"].max()), 65],
    }
    return q


def predictions_join(df: pd.DataFrame, pred: pd.DataFrame) -> dict:
    m = df.merge(pred, on="customer_id", how="outer", indicator=True)
    return {
        "dataset_rows": int(len(df)), "prediction_rows": int(len(pred)),
        "matched": int((m["_merge"] == "both").sum()),
        "dataset_only": int((m["_merge"] == "left_only").sum()),
        "predictions_only": int((m["_merge"] == "right_only").sum()),
        "churn_prob_missing": int(pred["churn_prob"].isna().sum()),
        "churn_prob_out_of_range": int(((pred["churn_prob"] < 0) | (pred["churn_prob"] > 1)).sum()),
        "actual_churn_equals_churn": bool((m["actual_churn"] == m["churn"]).all())
        if "actual_churn" in m else None,
        "prediction_source": {k: int(v) for k, v in pred["prediction_source"].value_counts().items()},
    }


# --------------------------------------------------------------------------
# CHURN-8: behaviour variables vs observed churn
# --------------------------------------------------------------------------
BEHAVIOUR = {
    # column: (bins or None for discrete, labels)
    "watch_hours_per_week": ([0, 2, 5, 10, 20, 40], ["0.5-2", "2-5", "5-10", "10-20", "20-40"]),
    "logins_last_30_days": ([-1, 5, 10, 15, 20, 60], ["0-5", "6-10", "11-15", "16-20", "21+"]),
    "payment_failures_3m": (None, None),
    "support_tickets": (None, None),
    "plan_type": (None, None),
    "tenure_months": ([0, 5, 12, 24, 48, 72], ["1-5", "6-12", "13-24", "25-48", "49-72"]),
}
NUMERIC_BEHAVIOUR = ["watch_hours_per_week", "logins_last_30_days",
                     "payment_failures_3m", "support_tickets", "tenure_months"]


def behaviour(df: pd.DataFrame) -> dict:
    y = df["churn"]
    out: dict = {}
    for col, (bins, labels) in BEHAVIOUR.items():
        s = df[col]
        entry: dict = {}
        if col in NUMERIC_BEHAVIOUR:
            d = s.describe(percentiles=[0.25, 0.5, 0.75])
            entry["distribution"] = {k: round(float(v), 2) for k, v in d.items()}
            entry["mean_churned"] = round(float(s[y == 1].mean()), 2)
            entry["mean_retained"] = round(float(s[y == 0].mean()), 2)
            a = auc(s, y)
            entry["auc"] = round(a, 3)
            entry["direction"] = "higher -> more churn" if a > 0.5 else "higher -> less churn"
            entry["strength_abs_auc_minus_0_5"] = round(abs(a - 0.5), 3)
            entry["point_biserial_r"] = round(float(np.corrcoef(s, y)[0, 1]), 3)
        else:
            entry["distribution"] = {k: int(v) for k, v in s.value_counts().items()}
        entry["cramers_v"] = round(cramers_v(s if bins is None else pd.cut(s, bins, labels=labels), y), 3)
        grp = df.assign(_g=s if bins is None else pd.cut(s, bins=bins, labels=labels))
        entry["churn_by_group"] = rate_table(grp, "_g")
        out[col] = entry
    ranking = sorted(out, key=lambda c: out[c]["cramers_v"], reverse=True)
    return {"overall_churn": {"n": int(len(df)), "churned": int(y.sum()),
                              "pct": round(100 * y.mean(), 1)},
            "variables": out, "ranking_by_cramers_v": ranking}


# --------------------------------------------------------------------------
# CHURN-9: observed churn by segment vs mean predicted probability (API basis)
# --------------------------------------------------------------------------
def segments(df: pd.DataFrame) -> dict:
    d = df.copy()
    d["tenure_bucket"] = pd.cut(d["tenure_months"], bins=API_TENURE_BINS, labels=API_TENURE_LABELS)
    d["age_band"] = pd.cut(d["age"], bins=[17, 24, 34, 44, 65], labels=["18-24", "25-34", "35-44", "45+"])
    one_way = {}
    for col in ["plan_type", "device_type", "tenure_bucket", "preferred_genre",
                "country", "gender", "payment_method", "age_band", "num_profiles"]:
        one_way[col] = {"rows": rate_table(d, col, extra_pred=True),
                        "cramers_v": round(cramers_v(d[col], d["churn"]), 3)}

    # Two-way segments, to find the genuinely high-risk combinations.
    d["pay_fail_band"] = np.where(d["payment_failures_3m"] >= 3, "3-4 failures",
                                  np.where(d["payment_failures_3m"] >= 1, "1-2 failures", "0 failures"))
    d["watch_band"] = pd.cut(d["watch_hours_per_week"], [0, 2, 5, 40], labels=["<2h", "2-5h", "5h+"])
    combos = [("plan_type", "device_type"), ("tenure_bucket", "watch_band"),
              ("tenure_bucket", "pay_fail_band"), ("watch_band", "pay_fail_band")]
    two_way = []
    for a, b in combos:
        for (va, vb), g in d.groupby([a, b], observed=True):
            n, k = len(g), int(g["churn"].sum())
            lo, hi = wilson(k, n)
            two_way.append({"segment": f"{a}={va} & {b}={vb}", "n": n, "churned": k,
                            "observed_churn_pct": round(100 * k / n, 1), "ci95_pct": [lo, hi],
                            "mean_predicted_pct": round(100 * g["churn_prob"].mean(), 1)})
    eligible = [r for r in two_way if r["n"] >= MIN_N]
    top = sorted(eligible, key=lambda r: r["observed_churn_pct"], reverse=True)[:8]
    low = sorted(eligible, key=lambda r: r["observed_churn_pct"])[:3]
    return {"one_way": one_way, "two_way_top": top, "two_way_lowest": low,
            "min_n_for_segment": MIN_N,
            "overall_observed_pct": round(100 * d["churn"].mean(), 1),
            "overall_mean_predicted_pct": round(100 * d["churn_prob"].mean(), 1)}


# --------------------------------------------------------------------------
# Charts
# --------------------------------------------------------------------------
def charts(df: pd.DataFrame, beh: dict, seg: dict) -> list[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    overall = beh["overall_churn"]["pct"]
    written = []

    # CHURN-8: observed churn by group for the six behaviour variables.
    fig, axes = plt.subplots(2, 3, figsize=(13, 7))
    for ax, col in zip(axes.flat, BEHAVIOUR):
        rows = beh["variables"][col]["churn_by_group"]
        labels = [r["group"] for r in rows]
        vals = [r["observed_churn_pct"] for r in rows]
        err = [[v - r["ci95_pct"][0] for v, r in zip(vals, rows)],
               [r["ci95_pct"][1] - v for v, r in zip(vals, rows)]]
        ax.bar(labels, vals, yerr=err, capsize=3, color="#4a5568")
        ax.axhline(overall, ls="--", lw=1, color="#c53030", label=f"overall {overall}%")
        for i, r in enumerate(rows):
            ax.text(i, 2, f"n={r['n']}", ha="center", fontsize=7, color="white")
        ax.set_title(f"{col}  (Cramér's V {beh['variables'][col]['cramers_v']})", fontsize=9)
        ax.set_ylabel("Observed churn (%)", fontsize=8)
        ax.set_ylim(0, 100)
        ax.tick_params(axis="x", labelsize=7, rotation=20)
        ax.legend(fontsize=7, loc="upper right")
    fig.suptitle("CHURN-8 — Observed churn rate by behaviour variable (95% Wilson CI)", fontsize=11)
    fig.tight_layout()
    p = FIG_DIR / "churn8_churn_rate_by_variable.png"
    fig.savefig(p, dpi=110)
    plt.close(fig)
    written.append(p)

    # CHURN-8: distributions of the numeric behaviour variables, by outcome.
    fig, axes = plt.subplots(1, 5, figsize=(16, 3.2))
    for ax, col in zip(axes, NUMERIC_BEHAVIOUR):
        for v, colr, lab in [(0, "#3182ce", "retained"), (1, "#c53030", "churned")]:
            ax.hist(df.loc[df["churn"] == v, col], bins=20, alpha=0.55, color=colr, label=lab, density=True)
        ax.set_title(col, fontsize=9)
        ax.set_ylabel("Density", fontsize=8)
        ax.tick_params(labelsize=7)
    axes[0].legend(fontsize=7)
    fig.suptitle("CHURN-8 — Distributions by observed outcome", fontsize=11)
    fig.tight_layout()
    p = FIG_DIR / "churn8_distributions.png"
    fig.savefig(p, dpi=110)
    plt.close(fig)
    written.append(p)

    # CHURN-9: observed churn vs mean predicted probability, on the API's groups.
    fig, axes = plt.subplots(1, 4, figsize=(16, 3.6))
    for ax, col in zip(axes, ["plan_type", "device_type", "tenure_bucket", "preferred_genre"]):
        rows = seg["one_way"][col]["rows"]
        x = np.arange(len(rows))
        ax.bar(x - 0.2, [r["observed_churn_pct"] for r in rows], 0.4, label="observed churn", color="#4a5568")
        ax.bar(x + 0.2, [r["mean_predicted_pct"] for r in rows], 0.4, label="mean predicted (API)", color="#a0aec0")
        ax.set_xticks(x, [r["group"] for r in rows], fontsize=7, rotation=25)
        ax.set_title(col, fontsize=9)
        ax.set_ylim(0, 100)
        ax.set_ylabel("%", fontsize=8)
    axes[0].legend(fontsize=7)
    fig.suptitle("CHURN-9 — Observed churn rate vs mean predicted churn probability", fontsize=11)
    fig.tight_layout()
    p = FIG_DIR / "churn9_observed_vs_predicted.png"
    fig.savefig(p, dpi=110)
    plt.close(fig)
    written.append(p)
    return [str(w.relative_to(ROOT)) for w in written]


def main() -> None:
    df = pd.read_csv(DATASET)
    pred = pd.read_csv(PREDICTIONS)
    q = quality(df)
    join = predictions_join(df, pred)
    merged = df.merge(pred[["customer_id", "churn_prob", "risk_level", "prediction_source"]],
                      on="customer_id", how="inner")
    beh = behaviour(df)
    seg = segments(merged)
    figs = charts(df, beh, seg)
    result = {
        "inputs": {
            "dataset": {"path": "backend/ott_churn_dataset.csv", "git_blob": git_blob(DATASET),
                        "sha256": hashlib.sha256(DATASET.read_bytes()).hexdigest()},
            "predictions": {"path": "backend/customer_predictions.csv", "git_blob": git_blob(PREDICTIONS),
                            "sha256": hashlib.sha256(PREDICTIONS.read_bytes()).hexdigest()},
        },
        "churn7_quality": q,
        "churn7_predictions_join": join,
        "churn8_behaviour": beh,
        "churn9_segments": seg,
        "figures": figs,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {OUT_JSON.relative_to(ROOT)} and {len(figs)} figures")


if __name__ == "__main__":
    main()
