"""CHURN-16 — Customer Lifetime Value formula and tier assignment."""
import math

import numpy as np
import pytest

import churniq_core as core
import churniq_ml_pipeline as pipeline


# ── Normal records ──────────────────────────────────────────────────────────
@pytest.mark.parametrize('charge,tenure,prob,expected', [
    (499, 42, 0.6173, 499 * 42 * (1 - 0.6173)),
    (799, 72, 0.0638, 799 * 72 * (1 - 0.0638)),
    (199, 12, 0.25,   199 * 12 * 0.75),
])
def test_clv_normal_records(charge, tenure, prob, expected):
    assert core.calc_clv(charge, tenure, prob) == round(expected, 2)


def test_clv_tenure_floor_of_six_months():
    assert core.calc_clv(199, 2, 0.5) == round(199 * 6 * 0.5, 2)
    assert core.calc_clv(199, 0, 0.5) == round(199 * 6 * 0.5, 2)
    assert core.calc_clv(199, 6, 0.5) == core.calc_clv(199, 5, 0.5)
    assert core.calc_clv(199, 7, 0.5) > core.calc_clv(199, 6, 0.5)


# ── Missing values ──────────────────────────────────────────────────────────
@pytest.mark.parametrize('args', [(None, 12, 0.3), (499, None, 0.3), (499, 12, None),
                                  (float('nan'), 12, 0.3), (499, 12, np.nan)])
def test_clv_missing_inputs_return_none(args):
    assert core.calc_clv(*args) is None


@pytest.mark.parametrize('clv', [None, float('nan'), np.nan])
def test_segment_of_missing_clv_is_unknown(clv):
    assert core.get_clv_segment(clv) == 'Unknown'


# ── Zero / negative / invalid ───────────────────────────────────────────────
def test_clv_zero_values():
    assert core.calc_clv(0, 12, 0.3) == 0.0          # free plan
    assert core.calc_clv(499, 12, 1.0) == 0.0        # certain churn
    assert core.calc_clv(499, 12, 0.0) == 499 * 12   # certain retention


@pytest.mark.parametrize('args', [(-1, 12, 0.3), (499, -1, 0.3), (499, 12, -0.01),
                                  (499, 12, 1.01), (499, 12, float('inf')),
                                  ('abc', 12, 0.3), (499, 'twelve', 0.3)])
def test_clv_invalid_inputs_raise(args):
    with pytest.raises(ValueError):
        core.calc_clv(*args)


def test_clv_accepts_numeric_strings():
    assert core.calc_clv('499', '12', '0.5') == round(499 * 12 * 0.5, 2)


# ── Tier boundaries ─────────────────────────────────────────────────────────
@pytest.mark.parametrize('clv,tier', [
    (0, 'Low'), (2999.99, 'Low'), (3000, 'Low'), (3000.01, 'Medium'),
    (7999.99, 'Medium'), (8000, 'Medium'), (8000.01, 'High'), (53857.7, 'High'),
])
def test_tier_boundaries(clv, tier):
    assert core.get_clv_segment(clv) == tier


def test_all_tier_functions_agree(api):
    main, _ = api
    for v in [0, 3000, 3000.01, 8000, 8000.01, 20000]:
        assert main.get_clv_segment(v) == pipeline.clv_segment(v) == core.get_clv_segment(v)


# ── Against the data and the API ────────────────────────────────────────────
def test_dataset_clv_matches_formula(artifacts):
    d = artifacts['base']
    recomputed = d['monthly_charge'] * np.maximum(d['tenure_months'], 6) * (1 - d['churn_probability'])
    # churn_probability is stored rounded to 4 dp → max error 799 × 72 × 0.00005 ≈ 2.9
    assert (recomputed - d['clv_score']).abs().max() < 2.9
    assert (d['clv_score'].map(core.get_clv_segment) == d['clv_segment']).all()


def test_api_clv_matches_hand_calculation_for_sample_customers(api):
    _, client = api
    # Customers either side of both tier boundaries + extremes (see docs/ml/04)
    for cid, tier in [('CUST02582', 'High'), ('CUST01546', 'Medium'), ('CUST01199', 'Medium'),
                      ('CUST03159', 'Low'), ('CUST02849', 'High'), ('CUST01033', 'Low')]:
        j = client.get(f'/customer/{cid}').json()
        hand = j['monthly_charge'] * max(j['tenure_months'], 6) * (1 - j['churn_prob'])
        assert abs(hand - j['clv_score']) < 3, cid          # churn_prob shown rounded to 4 dp
        assert j['clv_segment'] == tier == core.get_clv_segment(j['clv_score']), cid
        assert j['clv_breakdown']['formula'] == 'monthly_charge × max(tenure, 6) × (1 − churn_probability)'


def test_clv_tiers_consistent_across_endpoints(api):
    main, client = api
    scored = main.FULL_DF[main.FULL_DF['clv_score'].notna()]
    assert (scored['clv_segment'] == scored['clv_score'].map(core.get_clv_segment)).all()
    by_clv = client.get('/segments').json()['by_clv']
    assert sum(r['count'] for r in by_clv) == len(main.FULL_DF)
    kpis = client.get('/dashboard/summary').json()['kpis']
    high = scored[(scored['risk_level'] == 'HIGH') & (scored['clv_score'] > core.CLV_HIGH)]
    assert kpis['high_value_at_risk'] == len(high)
