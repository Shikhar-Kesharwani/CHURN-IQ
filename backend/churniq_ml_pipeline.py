# =============================================================================
#
#   ██████╗██╗  ██╗██╗   ██╗██████╗ ███╗   ██╗██╗ ██████╗
#  ██╔════╝██║  ██║██║   ██║██╔══██╗████╗  ██║██║██╔═══██╗
#  ██║     ███████║██║   ██║██████╔╝██╔██╗ ██║██║██║   ██║
#  ██║     ██╔══██║██║   ██║██╔══██╗██║╚██╗██║██║██║▄▄ ██║
#  ╚██████╗██║  ██║╚██████╔╝██║  ██║██║ ╚████║██║╚██████╔╝
#   ╚═════╝╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═══╝╚═╝ ╚══▀▀═╝
#
#   ChurnIQ Pro — FILE 1: Complete ML Pipeline
#   ─────────────────────────────────────────────────────────
#   What this file does (run top to bottom via main()):
#
#   PART A — DATASET GENERATION
#     Generates a synthetic OTT churn dataset (5000 customers)
#     using Faker + NumPy with business-rule-driven churn logic
#
#   PART B — EXPLORATORY DATA ANALYSIS (EDA)
#     Visually understands the data before training
#     Saves 6-chart EDA dashboard as PNG
#
#   PART C — PREPROCESSING & FEATURE ENGINEERING
#     Cleans data, encodes categories, engineers new features
#     Splits into train/test sets
#     (shared with the API through churniq_core.py — no training/serving skew)
#
#   PART D — SMOTE (Class Imbalance Fix)
#     Balances churned vs retained in training set ONLY
#
#   PART E — MODEL TRAINING (XGBoost)
#     Trains gradient boosted model, saves as .pkl
#
#   PART F — MODEL EVALUATION
#     Confusion matrix, ROC curve, feature importance
#
#   PART G — SHAP (Explainable AI)
#     Computes why each customer will churn
#     Saves summary + waterfall plots
#
#   PART H — PREDICTIONS TABLE
#     Generates final CSV with churn_prob, risk_level,
#     top 3 SHAP reasons, CLV score for every TEST customer
#
#   ─────────────────────────────────────────────────────────
#   HOW TO RUN:
#     pip install -r requirements-dev.txt
#     python churniq_ml_pipeline.py --output-dir ./pipeline_outputs
#
#   ⚠ WARNING: running with --output-dir . (backend/) OVERWRITES the committed
#     ott_churn_dataset.csv and customer_predictions.csv. The committed files
#     contain the email column and the CUST99999 demo customer added by
#     add_emails.py / fix_cust99999.py — re-run those scripts afterwards.
#     The default output directory is therefore ./pipeline_outputs/.
#
#   REPRODUCIBILITY (CHURN-13): with a fixed environment this pipeline is
#     deterministic (all seeds = 42). Retraining on Linux with the pinned
#     versions does NOT reproduce the committed churniq_model.pkl bit-for-bit
#     (see docs/ml/01-pipeline-review.md). Evaluate the committed artifact with
#     evaluate_model.py rather than retraining it.
#
#   OUTPUT FILES:
#     ott_churn_dataset.csv        ← raw dataset
#     churniq_model.pkl            ← trained XGBoost model
#     feature_names.pkl            ← feature column names
#     customer_predictions.csv     ← predictions + SHAP reasons
#     eda_dashboard.png            ← EDA plots
#     model_evaluation.png         ← confusion matrix + ROC
#     shap_summary.png             ← SHAP beeswarm
#     shap_importance.png          ← SHAP bar chart
#     shap_waterfall_example.png   ← individual customer
# =============================================================================

# ─── IMPORTS ──────────────────────────────────────────────────────────────────
# Plotting, Faker and SHAP are imported inside the functions that need them,
# so that tests and the evaluation script can import this module cheaply.
import argparse
import json
import os
import pickle
import random
import warnings

import numpy as np                # Math & array operations
import pandas as pd               # DataFrames — like Excel in Python

from sklearn.model_selection import train_test_split   # Split data train/test
from sklearn.metrics import (
    classification_report,        # Precision, Recall, F1 in one table
    confusion_matrix,             # TP, FP, TN, FN grid
    roc_auc_score,                # Area under ROC curve
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
)
from xgboost import XGBClassifier          # Our main ML model

import churniq_core as core

warnings.filterwarnings('ignore')

# ─── CONFIGURATION ────────────────────────────────────────────────────────────
SEED      = 42     # Fixed seed = same dataset, split, SMOTE and model every run
N         = 5000   # Number of customers to generate
TEST_SIZE = 0.20   # 20% held out for testing

# Training hyperparameters (recorded for CHURN-13 / reused by CHURN-17 research)
XGB_PARAMS = dict(
    n_estimators=200,         # 200 sequential trees
    max_depth=5,              # Max tree depth
    learning_rate=0.1,        # Step size (eta)
    subsample=0.8,            # Row subsampling
    colsample_bytree=0.8,     # Feature subsampling
    eval_metric='logloss',    # Binary cross-entropy loss
    random_state=SEED,
    verbosity=0,              # Suppress XGBoost internal logs
)
SMOTE_PARAMS = dict(random_state=SEED, k_neighbors=5)

# Model recipes. 'baseline' = the current production recipe (default).
# 'regularised' = CHURN-17 recommendation: shallower, slower-learning trees,
# no SMOTE. Selected by 5-fold CV on the training split only; on the held-out
# test split it improved ROC-AUC 0.724 → 0.758 (paired bootstrap 95% CI of the
# gain [+0.018, +0.052]) and improved calibration. See
# docs/ml/05-model-improvement-research.md. Switching production to it
# requires regenerating the committed artifacts — a team decision.
# Expected direction of churn risk as each feature INCREASES (CHURN-45,
# docs/ml/07-monotonic-constraints.md). Taken from the churn_score terms in
# generate_dataset: risk falls with watch hours, logins and tenure, and rises
# with payment failures and support tickets. Engineered features that /whatif
# recomputes from those inputs get the matching sign. Every other feature
# (incl. monthly_charge, which has no direct term) is unconstrained.
MONOTONE_DIRECTIONS = {
    'watch_hours_per_week': -1,
    'logins_last_30_days':  -1,
    'tenure_months':        -1,
    'payment_failures_3m':  +1,
    'support_tickets':      +1,
    'engagement_score':     -1,
    'friction_score':       +1,
    'is_new_customer':      +1,
}

_REGULARISED_PARAMS = dict(XGB_PARAMS, max_depth=2, learning_rate=0.03,
                           n_estimators=400, min_child_weight=1)

MODEL_CONFIGS = {
    'baseline':    {'xgb_params': XGB_PARAMS, 'smote': True, 'monotone': False},
    'regularised': {'xgb_params': _REGULARISED_PARAMS, 'smote': False, 'monotone': False},
    # CHURN-45 decision, adopted in CHURN-57: CHURN-17's regularised recipe plus
    # monotone constraints. Test ROC-AUC 0.760 (vs 0.724 for 'baseline'), and
    # What-If risk never moves against MONOTONE_DIRECTIONS for any customer.
    'regularised_monotonic': {'xgb_params': _REGULARISED_PARAMS, 'smote': False, 'monotone': True},
}

# The recipe that produces the committed production artifacts
# (churniq_model.pkl, oof_fold_models.pkl, customer_predictions.csv).
PRODUCTION_CONFIG = 'regularised_monotonic'


def monotone_constraint_tuple(columns) -> tuple:
    """XGBoost monotone_constraints in the given column order."""
    return tuple(int(MONOTONE_DIRECTIONS.get(c, 0)) for c in columns)


def xgb_params_for(model_config: str, columns) -> dict:
    """XGBoost parameters for a model config, with constraints for these columns."""
    cfg = MODEL_CONFIGS[model_config]
    params = dict(cfg['xgb_params'])
    if cfg.get('monotone'):
        params['monotone_constraints'] = monotone_constraint_tuple(columns)
    return params

# Rows that were appended to the dataset AFTER the pipeline ran (demo data).
# They were never part of the train/test split and must be excluded when the
# split is rebuilt for evaluation.
DEMO_CUSTOMER_IDS = {'CUST99999'}


# =============================================================================
#   PART A — DATASET GENERATION
# =============================================================================
# WHY SYNTHETIC DATA?
#   The standard Telco Churn dataset from Kaggle is overused —
#   every second ML student project uses it. A synthetic dataset:
#     1. Shows awareness of data privacy in ML
#     2. Lets us control feature richness
#     3. Lets us bake in realistic business logic
#     4. Makes the project unique and memorable
#
# HOW THE CHURN LOGIC WORKS:
#   We assign a "churn_score" to each customer based on real-world
#   OTT platform signals. The score is converted to a probability
#   using sigmoid function. Then we sample the actual churn label
#   from that probability (so it's probabilistic, not deterministic).
#
# VIVA TIP:
#   "We generated synthetic data to avoid using overused public datasets
#    and to demonstrate understanding of data privacy. The churn labels
#    are assigned using domain-knowledge-driven business rules, making
#    the data statistically realistic for an OTT platform."
# =============================================================================

# Real Netflix-style plans with Indian pricing
PLANS = {
    'Basic':    {'charge': 199,  'weight': 0.45},   # Most popular, cheapest
    'Standard': {'charge': 499,  'weight': 0.35},   # Mid-tier
    'Premium':  {'charge': 799,  'weight': 0.20},   # Least popular, most features
}
PAYMENT_METHODS = ['UPI', 'Credit Card', 'Debit Card', 'Wallet']
DEVICES         = ['Mobile', 'Laptop', 'Smart TV', 'Tablet']
GENRES          = ['Action', 'Drama', 'Comedy', 'Thriller', 'Kids', 'Documentary', 'Romance']
GENDERS         = ['Male', 'Female', 'Other']
# India-weighted country distribution (most OTT users are in India)
COUNTRIES = ['India'] * 80 + ['UAE', 'USA', 'UK', 'Singapore', 'Canada'] * 4


def sigmoid(x):
    """Convert any real number to a probability between 0 and 1."""
    return 1 / (1 + np.exp(-x))


def clv_segment(v):
    """Segment customers into High/Medium/Low CLV buckets (shared thresholds)."""
    return core.get_clv_segment(v)


def generate_dataset(n: int = N, seed: int = SEED, with_names: bool = True) -> pd.DataFrame:
    """
    Generate the synthetic OTT dataset. The random draw order is identical to
    the original script, so seed=42 reproduces the committed dataset's numeric
    columns exactly. Names come from Faker (en_IN) and are not seeded.
    """
    np.random.seed(seed)
    random.seed(seed)

    # ── Generate Base Features ────────────────────────────────────────────
    plan_types      = random.choices(list(PLANS.keys()),
                                     weights=[v['weight'] for v in PLANS.values()], k=n)
    monthly_charges = [PLANS[p]['charge'] for p in plan_types]
    tenures         = np.random.gamma(shape=2, scale=12, size=n).clip(1, 72).astype(int)
    ages            = np.random.normal(loc=30, scale=8, size=n).clip(18, 65).astype(int)

    # Watch behavior — exponential: most users watch little, few watch a lot
    watch_hours_per_week = np.random.exponential(scale=8, size=n).clip(0.5, 40).round(1)
    num_profiles         = np.random.choice([1, 2, 3, 4, 5],
                                            p=[0.30, 0.30, 0.20, 0.15, 0.05], size=n)
    logins_last_30_days  = np.random.poisson(lam=12, size=n).clip(0, 60)

    # Payment failures — most users have none, few have many
    payment_failures     = np.random.choice([0, 1, 2, 3, 4],
                                            p=[0.60, 0.20, 0.10, 0.07, 0.03], size=n)
    support_tickets      = np.random.choice([0, 1, 2, 3, 4, 5],
                                            p=[0.50, 0.25, 0.12, 0.07, 0.04, 0.02], size=n)

    # last_login_days_ago: most users logged in recently, some inactive
    last_login_days_ago  = np.random.exponential(scale=5, size=n).clip(0, 90).astype(int)

    genders         = random.choices(GENDERS,         k=n)
    countries       = random.choices(COUNTRIES,       k=n)
    payment_methods = random.choices(PAYMENT_METHODS, k=n)
    devices         = random.choices(DEVICES,         k=n)
    genre_prefs     = random.choices(GENRES,          k=n)

    # ── Churn Score Logic ─────────────────────────────────────────────────
    # Each behavioral signal contributes a "churn score" (domain knowledge):
    #   - Low engagement is the #1 predictor of churn
    #   - Payment failures strongly indicate financial churn
    #   - New customers (honeymoon period) are high risk
    #   - Long-tenure customers are loyal and less likely to churn
    churn_score = np.zeros(n)
    churn_score += np.where(watch_hours_per_week < 2,  1.5, 0)   # Almost no watching
    churn_score += np.where(watch_hours_per_week < 5,  0.5, 0)   # Below average watching
    churn_score += np.where(logins_last_30_days  < 3,  1.2, 0)   # Rarely logs in
    churn_score += np.where(last_login_days_ago  > 20, 1.0, 0)   # Gone dark 3+ weeks
    churn_score += np.where(last_login_days_ago  > 40, 0.8, 0)   # Very long absence
    churn_score += payment_failures * 0.6                         # Payment friction
    churn_score += support_tickets * 0.4                          # Support frustration
    churn_score += np.where(tenures < 3,  1.2, 0)                 # Very new: high risk
    churn_score += np.where(tenures < 6,  0.5, 0)                 # New: elevated risk
    churn_score += np.where(tenures > 24, -0.8, 0)                # 2+ years: loyalty
    churn_score += np.where(                                      # Price-sensitive segment
        (np.array(plan_types) == 'Basic') & (np.array(devices) == 'Mobile'), 0.4, 0)
    churn_score += np.random.normal(0, 0.5, n)                    # Realistic noise

    # Offset by -1.5 to get realistic ~40% base churn rate
    churn_prob = sigmoid(churn_score - 1.5)

    # Sample actual churn label from probability (probabilistic, not deterministic)
    churn_labels = (np.random.rand(n) < churn_prob).astype(int)

    # ── CLV (generator version) ─────────────────────────────────────────────
    # Uses the generator's TRUE churn probability → leakage column, never a
    # model input. Same formula as core.calc_clv.
    expected_tenure = np.where(tenures < core.CLV_MIN_TENURE, core.CLV_MIN_TENURE, tenures)
    clv_scores      = (np.array(monthly_charges) * expected_tenure * (1 - churn_prob)).round(2)
    clv_segments    = [clv_segment(v) for v in clv_scores]

    if with_names:
        from faker import Faker   # Generate realistic fake names
        fake = Faker('en_IN')
        names = [fake.name() for _ in range(n)]
    else:
        names = [f'Customer {i}' for i in range(1, n + 1)]

    return pd.DataFrame({
        'customer_id':           [f'CUST{str(i).zfill(5)}' for i in range(1, n + 1)],
        'name':                  names,
        'age':                   ages,
        'gender':                genders,
        'country':               countries,
        'plan_type':             plan_types,
        'monthly_charge':        monthly_charges,
        'tenure_months':         tenures,
        'watch_hours_per_week':  watch_hours_per_week,
        'num_profiles':          num_profiles,
        'logins_last_30_days':   logins_last_30_days,
        'last_login_days_ago':   last_login_days_ago,
        'preferred_genre':       genre_prefs,
        'device_type':           devices,
        'payment_method':        payment_methods,
        'payment_failures_3m':   payment_failures,
        'support_tickets':       support_tickets,
        'clv_score':             clv_scores,
        'clv_segment':           clv_segments,
        'churn_probability':     churn_prob.round(4),
        'churn':                 churn_labels,
    })


# =============================================================================
#   PART B — EXPLORATORY DATA ANALYSIS (EDA)
# =============================================================================
# CONCEPT: EDA = "Understanding your data before touching the model"
#   1. Churn distribution  → how balanced is our target?
#   2. Churn by plan type  → does plan affect churn?
#   3. Watch hours         → low watchers churn more?
#   4. Tenure vs churn     → new customers riskier?
#   5. Payment failures    → does friction predict churn?
#   6. Correlation heatmap → which numbers move together?
#
# VIVA TIP:
#   "EDA revealed that customers in the 0-3 month tenure bucket
#    have a much higher churn rate, leading us to engineer the
#    is_new_customer feature. Payment failures showed a near-linear
#    relationship with churn rate, motivating friction_score."
# =============================================================================

def save_eda_dashboard(df: pd.DataFrame, path: str) -> None:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import seaborn as sns

    churn_counts = df['churn'].value_counts().sort_index()
    churn_pct    = df['churn'].value_counts(normalize=True).sort_index() * 100

    fig, axes = plt.subplots(2, 3, figsize=(18, 10))
    fig.suptitle('ChurnIQ Pro — EDA Dashboard', fontsize=16, fontweight='bold')

    ax1 = axes[0, 0]
    ax1.bar(['Retained', 'Churned'], churn_counts.values, color=['#00C853', '#FF4444'], width=0.5)
    ax1.set_title('Churn Distribution', fontweight='bold')
    ax1.set_ylabel('Number of Customers')
    for i, v in enumerate(churn_counts.values):
        ax1.text(i, v + 30, f'{v}\n({churn_pct.values[i]:.1f}%)', ha='center', fontweight='bold')

    ax2 = axes[0, 1]
    churn_by_plan = df.groupby('plan_type')['churn'].mean() * 100
    bars = ax2.bar(churn_by_plan.index, churn_by_plan.values,
                   color=['#FF6B6B', '#4ECDC4', '#45B7D1'])
    ax2.set_title('Churn Rate by Plan Type', fontweight='bold')
    ax2.set_ylabel('Churn Rate (%)')
    for bar, val in zip(bars, churn_by_plan.values):
        ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                 f'{val:.1f}%', ha='center', fontweight='bold')

    ax3 = axes[0, 2]
    ax3.hist(df[df['churn'] == 0]['watch_hours_per_week'], bins=30, alpha=0.6,
             color='#00C853', label='Retained', density=True)
    ax3.hist(df[df['churn'] == 1]['watch_hours_per_week'], bins=30, alpha=0.6,
             color='#FF4444', label='Churned', density=True)
    ax3.set_title('Watch Hours Distribution', fontweight='bold')
    ax3.set_xlabel('Watch Hours per Week')
    ax3.set_ylabel('Density')
    ax3.legend()

    ax4 = axes[1, 0]
    tenure_bins  = pd.cut(df['tenure_months'], bins=[0, 3, 6, 12, 24, 72],
                          labels=['0-3m', '3-6m', '6-12m', '1-2yr', '2yr+'])
    churn_tenure = df.groupby(tenure_bins, observed=True)['churn'].mean() * 100
    ax4.plot(range(len(churn_tenure)), churn_tenure.values, 'o-', color='#FF6B35',
             linewidth=2.5, markersize=8)
    ax4.fill_between(range(len(churn_tenure)), churn_tenure.values, alpha=0.2, color='#FF6B35')
    ax4.set_title('Churn Rate by Tenure Bucket', fontweight='bold')
    ax4.set_xlabel('Tenure')
    ax4.set_ylabel('Churn Rate (%)')
    ax4.set_xticks(range(len(churn_tenure)))
    ax4.set_xticklabels(churn_tenure.index)

    ax5 = axes[1, 1]
    churn_payment = df.groupby('payment_failures_3m')['churn'].mean() * 100
    ax5.bar(churn_payment.index, churn_payment.values, color='#9B59B6', alpha=0.8)
    ax5.set_title('Churn Rate by Payment Failures', fontweight='bold')
    ax5.set_xlabel('Number of Payment Failures (last 3 months)')
    ax5.set_ylabel('Churn Rate (%)')

    ax6 = axes[1, 2]
    numeric_cols = ['tenure_months', 'watch_hours_per_week', 'logins_last_30_days',
                    'last_login_days_ago', 'payment_failures_3m', 'support_tickets',
                    'monthly_charge', 'churn']
    sns.heatmap(df[numeric_cols].corr(), annot=True, fmt='.2f', cmap='RdYlGn',
                center=0, ax=ax6, square=True, cbar_kws={'shrink': 0.8})
    ax6.set_title('Feature Correlation Heatmap', fontweight='bold')

    plt.tight_layout()
    plt.savefig(path, dpi=150, bbox_inches='tight')
    plt.close()


# =============================================================================
#   PART C — PREPROCESSING & FEATURE ENGINEERING
# =============================================================================
# CONCEPT: ML models only understand NUMBERS.
#
#   Label Encoding (plan_type): Basic=0, Standard=1, Premium=2
#     USE WHEN: There is a natural ORDER (Basic < Standard < Premium ✓)
#
#   One-Hot Encoding (gender, country, genre, device, payment method)
#     USE WHEN: No natural order (Mobile is NOT "less than" Laptop)
#     drop_first=True removes one redundant column per feature.
#
#   NO SCALING: tree models (XGBoost) split on thresholds, so feature scale
#   does not change the model. No StandardScaler is used — by design.
#
#   LEAKAGE CONTROL: customer_id, name, email (identifiers) and
#   churn_probability, clv_score, clv_segment (derived from the generator's
#   true churn probability) are dropped before training.
#
#   FEATURE ENGINEERING (see churniq_core.engineer_features):
#     engagement_score = watch_hours × logins / 30
#     friction_score   = payment_failures + support_tickets
#     inactivity_flag  = 1 if last_login > 14 days
#     is_new_customer  = 1 if tenure < 6 months
#
# The exact same code (churniq_core.encode_features) is used by main.py for
# live predictions — this is what guarantees no training/serving skew.
#
# VIVA TIP:
#   "We applied label encoding to plan_type because it has a natural
#    ordinal relationship (Basic < Standard < Premium). We used
#    one-hot encoding for device, genre, and payment method because
#    these are nominal — no inherent ordering exists between categories."
# =============================================================================

def preprocess(df: pd.DataFrame):
    """Return (X, y) — leakage columns dropped, features engineered and encoded."""
    model_df = df[~df['customer_id'].isin(DEMO_CUSTOMER_IDS)] if 'customer_id' in df else df
    return core.build_model_matrix(model_df)


def split_data(X: pd.DataFrame, y: pd.Series, test_size: float = TEST_SIZE, seed: int = SEED):
    """
    80/20 stratified split. Test data is NEVER seen during training.
    stratify=y keeps the churn ratio the same in train and test.
    """
    return train_test_split(X, y, test_size=test_size, random_state=seed, stratify=y)


# =============================================================================
#   PART D — SMOTE (Fix Class Imbalance)
# =============================================================================
# CONCEPT: Our dataset is ~57% retained / 43% churned.
#
# WHAT SMOTE DOES:
#   1. Takes a minority class sample (a churned customer)
#   2. Finds its K=5 nearest neighbors (other churned customers)
#   3. Creates a new SYNTHETIC sample by interpolating between them
#   4. Repeats until classes are 50/50
#
# KEY RULE → SMOTE ONLY ON TRAINING DATA:
#   apply_smote() is only ever called with the training split.
#   Test set must stay real-world distribution for honest evaluation.
#
# NOTE: imbalanced-learn returns synthetic rows with the input dtypes, so
#   integer/boolean columns stay integer/boolean (values are truncated).
#
# VIVA TIP:
#   "SMOTE is applied only to the training set. The test set represents
#    real-world distribution. We apply SMOTE after the split, never before,
#    to prevent data leakage from synthetic samples influencing test performance."
# =============================================================================

def apply_smote(X_train: pd.DataFrame, y_train: pd.Series, seed: int = SEED):
    from imblearn.over_sampling import SMOTE   # Fix class imbalance
    params = dict(SMOTE_PARAMS, random_state=seed)
    return SMOTE(**params).fit_resample(X_train, y_train)


# =============================================================================
#   PART E — MODEL TRAINING (XGBoost)
# =============================================================================
# CONCEPT: XGBoost = eXtreme Gradient Boosting — 200 small trees built
#   sequentially, each correcting the errors of the previous ones.
#
# KEY HYPERPARAMETERS (XGB_PARAMS above):
#   n_estimators=200, max_depth=5, learning_rate=0.1,
#   subsample=0.8, colsample_bytree=0.8, random_state=42
#
# CHANGE (CHURN-13): the original script passed eval_set=[(X_test, y_test)].
#   With no early stopping this did not change the model (verified: identical
#   predictions), but monitoring on the test set invites test-set tuning, so
#   it was removed. Use cross-validation on the training data for tuning.
#
# VIVA TIP:
#   "We chose XGBoost because it handles mixed feature types, missing values,
#    and imbalanced data well. It natively supports SHAP for explainability."
# =============================================================================

def train_model(X_train: pd.DataFrame, y_train: pd.Series, params: dict = None) -> XGBClassifier:
    model = XGBClassifier(**(params or XGB_PARAMS))
    model.fit(X_train, y_train, verbose=False)
    return model


# =============================================================================
#   PART F — MODEL EVALUATION
# =============================================================================
# NEVER judge a classification model on accuracy alone.
#   PRECISION = TP / (TP + FP)  "Of flagged churners, how many churned?"
#   RECALL    = TP / (TP + FN)  "Of actual churners, how many did we catch?"
#   F1        = harmonic mean of precision and recall
#   ROC-AUC   = ranking quality across ALL thresholds (0.5 = random)
#
# VIVA TIP:
#   "False Negatives (FN) are our most costly error — a churner we missed
#    will leave and we lose their CLV. We report recall alongside precision
#    and ROC-AUC rather than accuracy alone."
# =============================================================================

def evaluate(model, X_test: pd.DataFrame, y_test: pd.Series, threshold: float = 0.5) -> dict:
    """Compute the standard metric set on the held-out test split."""
    prob = model.predict_proba(X_test)[:, 1]
    pred = (prob >= threshold).astype(int)
    cm = confusion_matrix(y_test, pred, labels=[0, 1])
    tn, fp, fn, tp = (int(v) for v in cm.ravel())
    return {
        'threshold': threshold,
        'n_test':    int(len(y_test)),
        'accuracy':  float(accuracy_score(y_test, pred)),
        'precision': float(precision_score(y_test, pred, zero_division=0)),
        'recall':    float(recall_score(y_test, pred, zero_division=0)),
        'f1':        float(f1_score(y_test, pred, zero_division=0)),
        'roc_auc':   float(roc_auc_score(y_test, prob)),
        'confusion_matrix': {'tn': tn, 'fp': fp, 'fn': fn, 'tp': tp},
        'classification_report': classification_report(
            y_test, pred, target_names=['Retained', 'Churned'], output_dict=True, zero_division=0),
    }


def save_evaluation_plots(model, X_test, y_test, metrics: dict, path: str) -> None:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import seaborn as sns
    from sklearn.metrics import roc_curve

    prob = model.predict_proba(X_test)[:, 1]
    cmd = metrics['confusion_matrix']
    cm = np.array([[cmd['tn'], cmd['fp']], [cmd['fn'], cmd['tp']]])

    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    fig.suptitle('ChurnIQ Pro — Model Evaluation', fontsize=14, fontweight='bold')
    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', ax=axes[0],
                xticklabels=['Retained', 'Churned'], yticklabels=['Retained', 'Churned'])
    axes[0].set_title('Confusion Matrix', fontweight='bold')
    axes[0].set_ylabel('Actual')
    axes[0].set_xlabel('Predicted')

    fpr, tpr, _ = roc_curve(y_test, prob)
    axes[1].plot(fpr, tpr, color='#4A90E2', linewidth=2.5,
                 label=f"XGBoost (AUC = {metrics['roc_auc']:.3f})")
    axes[1].plot([0, 1], [0, 1], 'k--', linewidth=1, label='Random Baseline (AUC = 0.5)')
    axes[1].set_title('ROC Curve', fontweight='bold')
    axes[1].set_xlabel('False Positive Rate (False Alarms)')
    axes[1].set_ylabel('True Positive Rate (Churners Caught)')
    axes[1].legend(loc='lower right')
    axes[1].grid(True, alpha=0.3)

    feat_imp = pd.Series(model.feature_importances_, index=X_test.columns).nlargest(12)
    feat_imp[::-1].plot(kind='barh', ax=axes[2], color='#4A90E2')
    axes[2].set_title('Top 12 Feature Importances (XGBoost gain)', fontweight='bold')
    axes[2].set_xlabel('Importance Score')

    plt.tight_layout()
    plt.savefig(path, dpi=150, bbox_inches='tight')
    plt.close()


# =============================================================================
#   PART G — SHAP (EXPLAINABLE AI)
# =============================================================================
# SHAP = SHapley Additive exPlanations (cooperative game theory).
#   GLOBAL: Which features matter MOST across all customers? (beeswarm / bar)
#   LOCAL:  Why is THIS SPECIFIC customer at risk? (waterfall, top-3 reasons)
#
# UNITS: For XGBClassifier, TreeExplainer returns values in LOG-ODDS
#   (margin) units, not probability. expected_value + sum(shap) = margin and
#   sigmoid(margin) = predicted churn probability (validated in CHURN-15).
#   Positive value → pushed churn risk UP; negative → pushed it DOWN.
#
# VIVA TIP:
#   "We use TreeExplainer, which is optimized for tree-based models and
#    computes exact Shapley values efficiently. The local explanations
#    from SHAP feed our Gemini API prompt to generate personalized
#    retention strategies for each at-risk customer."
# =============================================================================

def compute_shap(model, X: pd.DataFrame):
    """Return (explainer, shap_values) for X using TreeExplainer."""
    import shap
    explainer = shap.TreeExplainer(model)
    return explainer, explainer.shap_values(X)


def save_shap_plots(explainer, shap_values, X_test, prob, output_dir: str) -> None:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import shap

    plt.figure(figsize=(12, 8))
    shap.summary_plot(shap_values, X_test, plot_type='dot', max_display=15, show=False)
    plt.title('SHAP Summary — Feature Impact on Churn Prediction (log-odds)\n'
              '(Right = Increases Churn Risk  |  Left = Reduces Churn Risk)',
              fontweight='bold', pad=15)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'shap_summary.png'), dpi=150, bbox_inches='tight')
    plt.close()

    plt.figure(figsize=(10, 7))
    shap.summary_plot(shap_values, X_test, plot_type='bar', max_display=12, show=False)
    plt.title('SHAP Feature Importance — Mean |SHAP| (log-odds)', fontweight='bold')
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'shap_importance.png'), dpi=150, bbox_inches='tight')
    plt.close()

    idx = int(np.argmax(prob))   # Most at-risk customer in test set
    plt.figure(figsize=(12, 6))
    shap.waterfall_plot(
        shap.Explanation(values=shap_values[idx], base_values=explainer.expected_value,
                         data=X_test.iloc[idx].values, feature_names=list(X_test.columns)),
        max_display=10, show=False)
    plt.title(f'SHAP Waterfall — Why Is This Customer Churning?\n'
              f'(Churn Probability: {prob[idx]:.1%})', fontweight='bold')
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'shap_waterfall_example.png'), dpi=150, bbox_inches='tight')
    plt.close()


# =============================================================================
#   PART H — PREDICTIONS TABLE
# =============================================================================
# Pre-compute predictions + SHAP reasons for the TEST customers and store
# them in a CSV that the FastAPI backend reads on startup (fast API).
#
#   customer_id, churn_prob, risk_level, top_reason_1/2/3,
#   clv_score (model-based CLV), actual_churn (ground truth)
#
# Only test customers are scored: scoring training customers with a model
# that was fit on them would give over-optimistic probabilities.
# =============================================================================

# Kept for backward compatibility with code importing them from this module
get_top_shap_reasons = core.get_top_shap_reasons
calc_clv             = core.calc_clv


def build_predictions(df: pd.DataFrame, X_test: pd.DataFrame, y_test: pd.Series,
                      prob: np.ndarray, shap_values: np.ndarray) -> pd.DataFrame:
    rows = []
    cols = list(X_test.columns)
    for i in range(len(X_test)):
        reasons  = core.get_top_shap_reasons(shap_values[i], cols)
        p        = float(prob[i])
        orig_idx = X_test.index[i]
        rows.append({
            'customer_id':  df.loc[orig_idx, 'customer_id'],
            'churn_prob':   round(p, 4),
            'risk_level':   core.get_risk_level(p),
            'top_reason_1': reasons[0] if len(reasons) > 0 else 'N/A',
            'top_reason_2': reasons[1] if len(reasons) > 1 else 'N/A',
            'top_reason_3': reasons[2] if len(reasons) > 2 else 'N/A',
            'clv_score':    core.calc_clv(df.loc[orig_idx, 'monthly_charge'],
                                          df.loc[orig_idx, 'tenure_months'], p),
            'actual_churn': int(y_test.iloc[i]),
        })
    return pd.DataFrame(rows).sort_values('churn_prob', ascending=False)


# =============================================================================
#   PART H2 — OUT-OF-FOLD PREDICTIONS FOR TRAINING CUSTOMERS (CHURN-37)
# =============================================================================
# The production model was trained on the 4,000 training customers, so its
# predictions for them are in-sample and badly over-confident (AUC 0.958 vs
# 0.717 on unseen data). Instead each training customer is scored by a model
# that never saw them: 5-fold stratified CV over the training split, the SAME
# recipe as production (SMOTE inside the training folds only + XGB_PARAMS),
# predicting the held-out fold. SHAP reasons come from that fold's own model.
# The fold models are saved so live what-if calls for these customers use the
# same model that produced their displayed probability.
#
# The generator's 'churn_probability' column is never used as a prediction.
# =============================================================================

OOF_N_SPLITS = 5


def oof_folds(X_train: pd.DataFrame, y_train: pd.Series, n_splits: int = OOF_N_SPLITS,
              seed: int = SEED):
    from sklearn.model_selection import StratifiedKFold
    return list(StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)
                .split(X_train, y_train))


def build_oof_predictions(df: pd.DataFrame, X_train: pd.DataFrame, y_train: pd.Series,
                          model_config: str = PRODUCTION_CONFIG, n_splits: int = OOF_N_SPLITS,
                          seed: int = SEED):
    """Return (predictions DataFrame for all training customers, list of fold models)."""
    cfg = MODEL_CONFIGS[model_config]
    parts, models = [], []
    for fold, (tr, va) in enumerate(oof_folds(X_train, y_train, n_splits, seed)):
        X_fit, y_fit = X_train.iloc[tr], y_train.iloc[tr]
        if cfg['smote']:
            X_fit, y_fit = apply_smote(X_fit, y_fit, seed)
        fold_model = train_model(X_fit, y_fit, xgb_params_for(model_config, X_train.columns))
        X_val, y_val = X_train.iloc[va], y_train.iloc[va]
        prob = fold_model.predict_proba(X_val)[:, 1]
        _, shap_values = compute_shap(fold_model, X_val)
        part = build_predictions(df, X_val, y_val, prob, shap_values)
        part['prediction_source'] = 'cv_out_of_fold'
        part['fold'] = fold
        parts.append(part)
        models.append(fold_model)
    return pd.concat(parts, ignore_index=True), models


def finalise_predictions(*parts: pd.DataFrame) -> pd.DataFrame:
    """Combine prediction parts into the customer_predictions.csv layout (deterministic order)."""
    out = pd.concat(parts, ignore_index=True)
    out['fold'] = out['fold'].astype('Int64')
    cols = ['customer_id', 'churn_prob', 'risk_level', 'top_reason_1', 'top_reason_2',
            'top_reason_3', 'clv_score', 'actual_churn', 'prediction_source', 'fold']
    out = out[cols].sort_values(['churn_prob', 'customer_id'], ascending=[False, True],
                                kind='mergesort').reset_index(drop=True)
    assert out['customer_id'].is_unique, 'duplicate customer_id in predictions'
    return out


# =============================================================================
#   MAIN
# =============================================================================

def main(output_dir: str = 'pipeline_outputs', make_plots: bool = True,
         model_config: str = PRODUCTION_CONFIG, dataset_path: str = None) -> dict:
    """
    Full pipeline. With dataset_path, train on that existing dataset instead of
    generating one (names/emails/demo rows are kept), write only the model,
    feature names and model_metadata.json, then stop: run
    generate_predictions.py next to rebuild predictions and fold models.
    """
    config = MODEL_CONFIGS[model_config]
    os.makedirs(output_dir, exist_ok=True)
    out = lambda name: os.path.join(output_dir, name)

    print("=" * 65)
    print("   ChurnIQ Pro — ML Pipeline")
    print("   OTT Subscription Churn Prediction System")
    print("=" * 65)

    if dataset_path:
        print(f"\n  PART A — DATASET (existing: {dataset_path})")
        df = pd.read_csv(dataset_path)
        make_plots = False
    else:
        print("\n  PART A — DATASET GENERATION")
        df = generate_dataset()
        df.to_csv(out('ott_churn_dataset.csv'), index=False)
    print(f"    {len(df)} customers | churn rate {df['churn'].mean():.1%}")

    if make_plots:
        print("\n  PART B — EDA")
        save_eda_dashboard(df, out('eda_dashboard.png'))

    print("\n  PART C — PREPROCESSING")
    X, y = preprocess(df)
    X_train, X_test, y_train, y_test = split_data(X, y)
    print(f"    X {X.shape} | train {len(X_train)} ({y_train.mean():.1%} churn) "
          f"| test {len(X_test)} ({y_test.mean():.1%} churn)")

    if config['smote']:
        print("\n  PART D — SMOTE (training split only)")
        X_train_fit, y_train_fit = apply_smote(X_train, y_train)
        print(f"    {len(X_train)} → {len(X_train_fit)} rows, classes {y_train_fit.value_counts().to_dict()}")
    else:
        print("\n  PART D — SMOTE skipped (model config: %s)" % model_config)
        X_train_fit, y_train_fit = X_train, y_train

    print(f"\n  PART E — TRAINING (model config: {model_config})")
    params = xgb_params_for(model_config, X.columns)
    model = train_model(X_train_fit, y_train_fit, params)
    with open(out('churniq_model.pkl'), 'wb') as f:
        pickle.dump(model, f)
    with open(out('feature_names.pkl'), 'wb') as f:
        pickle.dump(list(X.columns), f)
    print(f"    Model + {X.shape[1]} feature names saved")

    print("\n  PART F — EVALUATION (held-out test split)")
    metrics = evaluate(model, X_test, y_test)
    for k in ('accuracy', 'precision', 'recall', 'f1', 'roc_auc'):
        print(f"    {k:<10}: {metrics[k]:.4f}")

    import xgboost
    with open(out('model_metadata.json'), 'w') as f:
        json.dump({
            'model_config': model_config, 'smote': config['smote'], 'seed': SEED,
            'xgb_params': {k: (list(v) if isinstance(v, tuple) else v) for k, v in params.items()},
            'monotone_directions': MONOTONE_DIRECTIONS if config.get('monotone') else {},
            'split': {'test_size': TEST_SIZE, 'stratified': True, 'random_state': SEED},
            'train_rows': int(len(X_train)), 'test_rows': int(len(X_test)),
            'dataset': dataset_path or 'generated (generate_dataset, seed %d)' % SEED,
            'test_metrics': {k: round(metrics[k], 4)
                             for k in ('accuracy', 'precision', 'recall', 'f1', 'roc_auc')},
            'xgboost_version': xgboost.__version__,
        }, f, indent=2)

    if dataset_path:
        print("\n  Model trained on the existing dataset. Next: python generate_predictions.py")
        return metrics
    if make_plots:
        save_evaluation_plots(model, X_test, y_test, metrics, out('model_evaluation.png'))

    print("\n  PART G — SHAP")
    explainer, shap_values = compute_shap(model, X_test)
    prob = model.predict_proba(X_test)[:, 1]
    if make_plots:
        save_shap_plots(explainer, shap_values, X_test, prob, output_dir)

    print("\n  PART H — PREDICTIONS TABLE")
    test_df = build_predictions(df, X_test, y_test, prob, shap_values)
    test_df['prediction_source'] = 'holdout_test'
    test_df['fold'] = pd.NA

    print("\n  PART H2 — OUT-OF-FOLD PREDICTIONS (training customers)")
    oof_df, fold_models = build_oof_predictions(df, X_train, y_train, model_config)
    with open(out('oof_fold_models.pkl'), 'wb') as f:
        pickle.dump({'models': fold_models, 'feature_names': list(X.columns),
                     'model_config': model_config, 'n_splits': OOF_N_SPLITS, 'seed': SEED}, f)

    pred_df = finalise_predictions(test_df, oof_df)
    pred_df.to_csv(out('customer_predictions.csv'), index=False)
    print(f"    {len(pred_df)} predictions ({len(test_df)} held-out test + {len(oof_df)} "
          f"out-of-fold) → {out('customer_predictions.csv')}")
    print("\n  PIPELINE COMPLETE")
    return metrics


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run the ChurnIQ ML pipeline.')
    parser.add_argument('--output-dir', default='pipeline_outputs',
                        help="Where to write artifacts (default: pipeline_outputs/). "
                             "Using '.' overwrites the committed backend files.")
    parser.add_argument('--no-plots', action='store_true', help='Skip PNG generation.')
    parser.add_argument('--model-config', choices=sorted(MODEL_CONFIGS), default=PRODUCTION_CONFIG,
                        help="'regularised_monotonic' = production (CHURN-45/57); "
                             "'baseline' = previous production recipe; "
                             "'regularised' = CHURN-17 recipe without constraints.")
    parser.add_argument('--from-dataset', default=None,
                        help="Train on an existing dataset CSV instead of generating one, "
                             "write only the model, feature names and model_metadata.json.")
    args = parser.parse_args()
    main(args.output_dir, make_plots=not args.no_plots, model_config=args.model_config,
         dataset_path=args.from_dataset)
