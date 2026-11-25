"""CHURN-7: data-quality checks on backend/ott_churn_dataset.csv.

These guard the assumptions the pipeline and the API make about the raw data:
no missing values, unique customer IDs, values inside the generator's domains,
prices that match the plan, a binary label, and a prediction for every
customer. Full analysis and counts: docs/data/01-data-quality.md.
"""
import os
import re

import pandas as pd
import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

NUMERIC_RANGES = {
    'age': (18, 65),
    'tenure_months': (1, 72),
    'watch_hours_per_week': (0.5, 40.0),
    'num_profiles': (1, 5),
    'logins_last_30_days': (0, 60),
    'last_login_days_ago': (0, 90),
    'payment_failures_3m': (0, 4),
    'support_tickets': (0, 5),
    'churn_probability': (0.0, 1.0),
}
CATEGORIES = {
    'gender': {'Male', 'Female', 'Other'},
    'country': {'India', 'UAE', 'USA', 'UK', 'Singapore', 'Canada'},
    'plan_type': {'Basic', 'Standard', 'Premium'},
    'preferred_genre': {'Action', 'Drama', 'Comedy', 'Thriller', 'Kids', 'Documentary', 'Romance'},
    'device_type': {'Mobile', 'Laptop', 'Smart TV', 'Tablet'},
    'payment_method': {'UPI', 'Credit Card', 'Debit Card', 'Wallet'},
    'clv_segment': {'High', 'Medium', 'Low'},
}
PLAN_PRICE = {'Basic': 199, 'Standard': 499, 'Premium': 799}


@pytest.fixture(scope='module')
def df():
    return pd.read_csv(os.path.join(BACKEND_DIR, 'ott_churn_dataset.csv'))


def test_shape_and_columns(df):
    assert df.shape == (5001, 22)


def test_no_missing_or_blank_values(df):
    assert int(df.isna().sum().sum()) == 0
    for col in df.select_dtypes(include='object'):
        assert (df[col].astype(str).str.strip() == '').sum() == 0, col


def test_customer_ids_unique_and_well_formed(df):
    assert not df['customer_id'].duplicated().any()
    assert not df['customer_id'].str.strip().str.upper().duplicated().any()
    assert df['customer_id'].map(lambda s: bool(re.fullmatch(r'CUST\d{5}', s))).all()


def test_no_duplicate_rows(df):
    assert not df.duplicated().any()
    assert not df.drop(columns=['customer_id']).duplicated().any()


@pytest.mark.parametrize('col,bounds', NUMERIC_RANGES.items())
def test_numeric_values_in_generator_domain(df, col, bounds):
    lo, hi = bounds
    assert df[col].between(lo, hi).all(), f'{col} outside [{lo}, {hi}]'


@pytest.mark.parametrize('col,allowed', CATEGORIES.items())
def test_categorical_values_known(df, col, allowed):
    assert set(df[col].unique()) <= allowed


def test_price_matches_plan(df):
    assert (df['monthly_charge'] == df['plan_type'].map(PLAN_PRICE)).all()


def test_churn_label_binary(df):
    assert set(df['churn'].unique()) <= {0, 1}


def test_every_customer_has_a_prediction(df):
    pred = pd.read_csv(os.path.join(BACKEND_DIR, 'customer_predictions.csv'))
    assert set(pred['customer_id']) == set(df['customer_id'])
    assert pred['churn_prob'].between(0, 1).all()
