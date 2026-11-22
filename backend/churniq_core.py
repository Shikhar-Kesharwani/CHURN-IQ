# =============================================================================
#   ChurnIQ Pro — Shared ML Core (feature engineering, encoding, risk, CLV)
# =============================================================================
#   Single source of truth for logic that BOTH the training pipeline
#   (churniq_ml_pipeline.py) and the FastAPI backend (main.py) must apply
#   identically. Keeping it in one module prevents training/serving skew.
#
#   Why this module exists (CHURN-13):
#     main.build_feature_row() used to one-hot encode a SINGLE customer row
#     with pd.get_dummies(..., drop_first=True). With one row, each
#     categorical column has exactly one level, and drop_first removes it —
#     so every one-hot column was silently 0 at prediction time. The model
#     therefore saw every customer as Female / Canada / Action / Laptop /
#     Credit Card in POST /whatif. encode_features() below fixes this by
#     encoding against the fixed category levels seen during training.
# =============================================================================

from __future__ import annotations

import math
from typing import Iterable, List, Optional, Sequence

import numpy as np
import pandas as pd

# ─── Column groups ────────────────────────────────────────────────────────────
TARGET_COL = 'churn'

# Identifiers — no predictive meaning, must never reach the model
ID_COLS = ['customer_id', 'name', 'email']

# Target leakage — all derived from the generator's true churn probability
LEAKAGE_COLS = ['churn_probability', 'clv_score', 'clv_segment']

# Ordinal encoding: Basic < Standard < Premium
PLAN_ORDER = {'Basic': 0, 'Standard': 1, 'Premium': 2}

# Nominal categoricals → one-hot with drop_first=True.
# Levels are listed in the sorted order pandas uses, so the FIRST level is
# the dropped baseline exactly as in the original training run.
CATEGORY_LEVELS = {
    'gender':          ['Female', 'Male', 'Other'],
    'country':         ['Canada', 'India', 'Singapore', 'UAE', 'UK', 'USA'],
    'preferred_genre': ['Action', 'Comedy', 'Documentary', 'Drama', 'Kids',
                        'Romance', 'Thriller'],
    'device_type':     ['Laptop', 'Mobile', 'Smart TV', 'Tablet'],
    'payment_method':  ['Credit Card', 'Debit Card', 'UPI', 'Wallet'],
}
OHE_COLS = list(CATEGORY_LEVELS)

# ─── Feature engineering thresholds ───────────────────────────────────────────
INACTIVITY_DAYS     = 14   # inactivity_flag = last_login_days_ago > 14
NEW_CUSTOMER_MONTHS = 6    # is_new_customer = tenure_months < 6

# ─── Risk thresholds (on model churn probability) ─────────────────────────────
RISK_HIGH   = 0.70
RISK_MEDIUM = 0.40

# ─── CLV constants ────────────────────────────────────────────────────────────
CLV_MIN_TENURE = 6       # tenure floor used in the CLV formula (months)
CLV_HIGH       = 8000.0  # clv >  8000 → High
CLV_MEDIUM     = 3000.0  # clv >  3000 → Medium, otherwise Low


# =============================================================================
#   Feature engineering + encoding
# =============================================================================

def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add the 4 engineered features. Returns a copy; input is not modified."""
    out = df.copy()
    out['engagement_score'] = (
        out['watch_hours_per_week'] * out['logins_last_30_days'] / 30
    ).round(3)
    out['friction_score']  = out['payment_failures_3m'] + out['support_tickets']
    out['inactivity_flag'] = (out['last_login_days_ago'] > INACTIVITY_DAYS).astype(int)
    out['is_new_customer'] = (out['tenure_months'] < NEW_CUSTOMER_MONTHS).astype(int)
    return out


def encode_features(df: pd.DataFrame,
                    feature_names: Optional[Sequence[str]] = None) -> pd.DataFrame:
    """
    Turn raw customer rows into the model's feature matrix.

    Works identically for the full training table and for a single row:
    categoricals are encoded against CATEGORY_LEVELS, not against whatever
    levels happen to be present in `df`.

    - Identifier, leakage and target columns are dropped if present.
    - Unknown plan types become NaN (XGBoost treats NaN as missing).
    - Unknown categorical levels encode as all-zeros (= the baseline level).
    - If feature_names is given, columns are reordered to match it and any
      absent column is filled with 0.
    """
    out = engineer_features(df)
    out = out.drop(columns=[c for c in ID_COLS + LEAKAGE_COLS + [TARGET_COL]
                            if c in out.columns])
    out['plan_type'] = out['plan_type'].map(PLAN_ORDER)

    for col, levels in CATEGORY_LEVELS.items():
        if col in out.columns:
            out[col] = pd.Categorical(out[col], categories=levels)
    out = pd.get_dummies(out, columns=[c for c in OHE_COLS if c in out.columns],
                         drop_first=True)

    if feature_names is not None:
        out = out.reindex(columns=list(feature_names), fill_value=0)
    return out


def build_model_matrix(df: pd.DataFrame):
    """Return (X, y) for training from the raw dataset table."""
    y = df[TARGET_COL].astype(int)
    X = encode_features(df)
    return X, y


# =============================================================================
#   Risk level
# =============================================================================

def get_risk_level(prob: float) -> str:
    """HIGH (≥0.70) / MEDIUM (0.40–0.70) / LOW (<0.40)."""
    if prob >= RISK_HIGH:
        return 'HIGH'
    if prob >= RISK_MEDIUM:
        return 'MEDIUM'
    return 'LOW'


# =============================================================================
#   SHAP reasons
# =============================================================================

def get_top_shap_reasons(shap_row: Iterable[float], feature_cols: List[str],
                         n: int = 3) -> List[str]:
    """
    Top-n features with POSITIVE SHAP value (pushing churn risk up),
    formatted as "feature (impact: +X.XX)". SHAP units are log-odds.
    """
    pairs = sorted(zip(feature_cols, shap_row), key=lambda x: x[1], reverse=True)
    return [f"{feat} (impact: {val:+.2f})" for feat, val in pairs[:n] if val > 0]


# Human-readable names for one-hot groups
_OHE_LABELS = {
    'gender': 'Gender', 'country': 'Country', 'preferred_genre': 'Preferred genre',
    'device_type': 'Device', 'payment_method': 'Payment method',
}

# feature → (condition under which the strong statement is TRUE, statement)
# The statement is only shown when the customer's actual value satisfies the
# condition; otherwise a neutral, value-based description is used (CHURN-15).
_STRONG_CLAIMS = {
    'watch_hours_per_week': (lambda v: v < 5,
                             lambda v: f'Very low content engagement — only {v:.1f} watch hours/week'),
    'tenure_months':        (lambda v: v < NEW_CUSTOMER_MONTHS,
                             lambda v: f"Short subscription tenure — {v:.0f} month{'' if v == 1 else 's'}, "
                                       f"still in the high-risk early phase"),
    'is_new_customer':      (lambda v: v == 1,
                             lambda v: 'New customer — within the high-churn 0-6 month window'),
    'engagement_score':     (lambda v: v < 3,
                             lambda v: f'Low overall engagement score ({v:.2f}; watch hours × logins / 30)'),
    'logins_last_30_days':  (lambda v: v < 3,
                             lambda v: f'Infrequent logins — only {v:.0f} in the last 30 days'),
    'last_login_days_ago':  (lambda v: v > INACTIVITY_DAYS,
                             lambda v: f'Has not logged in for {v:.0f} days — going inactive'),
    'inactivity_flag':      (lambda v: v == 1,
                             lambda v: 'Customer has gone inactive — 14+ days without login'),
    'payment_failures_3m':  (lambda v: v > 0,
                             lambda v: f'Recent payment failures — {v:.0f} in the last 3 months (billing friction)'),
    'support_tickets':      (lambda v: v > 0,
                             lambda v: f'{v:.0f} support ticket(s) — experiencing service issues'),
    'friction_score':       (lambda v: v > 0,
                             lambda v: f'High friction score — {v:.0f} combined payment failures + support tickets'),
    'num_profiles':         (lambda v: v <= 1,
                             lambda v: 'Only 1 profile in use — subscription underutilized'),
}

# feature → neutral description of the actual value
_NEUTRAL = {
    'watch_hours_per_week': lambda v: f'Watch time of {v:.1f} hours/week',
    'tenure_months':        lambda v: f'Subscription tenure of {v:.0f} months',
    'is_new_customer':      lambda v: 'Tenure of 6+ months (not a new customer)',
    'engagement_score':     lambda v: f'Engagement score of {v:.2f} (watch hours × logins / 30)',
    'logins_last_30_days':  lambda v: f'{v:.0f} logins in the last 30 days',
    'last_login_days_ago':  lambda v: f'Last login {v:.0f} day(s) ago',
    'inactivity_flag':      lambda v: 'Logged in within the last 14 days',
    'payment_failures_3m':  lambda v: 'No payment failures in the last 3 months',
    'support_tickets':      lambda v: 'No support tickets raised',
    'friction_score':       lambda v: 'No payment failures or support tickets',
    'num_profiles':         lambda v: f'{v:.0f} profiles on the account',
    'monthly_charge':       lambda v: f'Monthly charge of ₹{v:.0f}',
    'age':                  lambda v: f'Customer age {v:.0f}',
    'plan_type':            lambda v: 'Plan: ' + {0: 'Basic', 1: 'Standard', 2: 'Premium'}.get(int(v), str(v)),
}


def describe_reason(feature: str, value=None) -> Optional[str]:
    """
    Plain-English description of a churn reason that is TRUE for the
    customer's actual feature value. Returns None if no description is known
    (callers then fall back to a title-cased feature name).

    Every reason passed here has a positive SHAP value, so the wording
    "raises predicted churn risk" is appended by the caller.
    """
    if value is None or _is_missing(value):
        return None
    for group, label in _OHE_LABELS.items():
        prefix = group + '_'
        if feature.startswith(prefix):
            level = feature[len(prefix):]
            return f'{label}: {level}' if float(value) >= 0.5 else f'{label}: not {level}'
    v = float(value)
    if feature in _STRONG_CLAIMS:
        condition, text = _STRONG_CLAIMS[feature]
        if condition(v):
            return text(v)
    if feature in _NEUTRAL:
        return _NEUTRAL[feature](v) + ' — raises predicted churn risk'
    return None


# =============================================================================
#   Customer Lifetime Value (CHURN-16)
# =============================================================================

def _is_missing(v) -> bool:
    if v is None:
        return True
    try:
        return math.isnan(float(v))
    except (TypeError, ValueError):
        return False


def calc_clv(monthly_charge, tenure, churn_prob) -> Optional[float]:
    """
    CLV = monthly_charge × max(tenure_months, 6) × (1 − churn_probability)

    Returns None if any input is missing (None/NaN) — a missing churn
    probability must not be silently treated as 0 % risk.
    Raises ValueError for invalid inputs: non-numeric values, negative
    monthly_charge or tenure, or churn_prob outside [0, 1].
    """
    if any(_is_missing(v) for v in (monthly_charge, tenure, churn_prob)):
        return None
    try:
        charge, ten, prob = float(monthly_charge), float(tenure), float(churn_prob)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"CLV inputs must be numeric: {exc}") from exc
    if not all(map(math.isfinite, (charge, ten, prob))):
        raise ValueError("CLV inputs must be finite numbers")
    if charge < 0:
        raise ValueError(f"monthly_charge must be >= 0, got {charge}")
    if ten < 0:
        raise ValueError(f"tenure must be >= 0, got {ten}")
    if not 0.0 <= prob <= 1.0:
        raise ValueError(f"churn_prob must be in [0, 1], got {prob}")
    return round(charge * max(ten, CLV_MIN_TENURE) * (1 - prob), 2)


def get_clv_segment(clv) -> str:
    """High (> 8000) / Medium (> 3000) / Low (≤ 3000); 'Unknown' if missing."""
    if _is_missing(clv):
        return 'Unknown'
    clv = float(clv)
    if clv > CLV_HIGH:
        return 'High'
    if clv > CLV_MEDIUM:
        return 'Medium'
    return 'Low'
