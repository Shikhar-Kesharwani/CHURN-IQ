"""CHURN-23 — KNN customer similarity (POST /customer-similarity, /api/customer-similarity).

Neighbour order, counts and self-exclusion are verified against an
independent brute-force Euclidean search over the engine's own preprocessing,
so the tests do not merely re-read the engine's output.
"""
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sklearn.preprocessing import StandardScaler

import customer_similarity as cs
from customer_similarity import CustomerSimilarityEngine


@pytest.fixture(scope='module')
def client(api):
    return TestClient(api[0].app, raise_server_exceptions=False)


@pytest.fixture(scope='module')
def space(api):
    """The engine's normalised feature matrix for every indexed customer."""
    engine = api[0].SIMILARITY_ENGINE
    X = engine.pipeline.transform(engine._prepare_dataframe(api[0].DATASET_DF))
    return pd.Index(api[0].DATASET_DF['customer_id']), np.asarray(X)


@pytest.fixture(scope='module')
def sample_ids(api):
    p = api[0].PREDICTIONS_DF
    return (list(p.loc[p['prediction_source'] == 'holdout_test', 'customer_id'][::100])
            + list(p.loc[p['prediction_source'] == 'cv_out_of_fold', 'customer_id'][::400])
            + ['CUST99999'])


def _brute_force(space, cid, n):
    ids, X = space
    i = ids.get_loc(cid)
    d = np.sqrt(((X - X[i]) ** 2).sum(axis=1))
    order = [j for j in np.argsort(d, kind='stable') if ids[j] != cid][:n]
    return [ids[j] for j in order], d[order]


def _similar(client, cid, n=None, path='/api/customer-similarity'):
    body = {'customer_id': cid} if n is None else {'customer_id': cid, 'n_neighbors': n}
    r = client.post(path, json=body)
    assert r.status_code == 200, r.text
    return r.json()


# ── Order, count, self-exclusion ─────────────────────────────────────────────
@pytest.mark.parametrize('n', [1, 3, 5, 10, 50])
def test_count_order_and_self_exclusion(client, sample_ids, n):
    for cid in sample_ids:
        body = _similar(client, cid, n)
        nb = body['similar_customers']
        assert body['count'] == len(nb) == n
        ids = [c['customer_id'] for c in nb]
        assert cid not in ids and len(set(ids)) == n
        d = [c['distance'] for c in nb]
        s = [c['similarity_score'] for c in nb]
        assert d == sorted(d), (cid, d)                       # closest first
        assert s == sorted(s, reverse=True), (cid, s)


def test_neighbours_match_independent_brute_force_search(client, space, sample_ids):
    for cid in sample_ids:
        body = _similar(client, cid, 10)
        expected_ids, expected_d = _brute_force(space, cid, 10)
        got_d = np.array([c['distance'] for c in body['similar_customers']])
        np.testing.assert_allclose(got_d, np.round(expected_d, 4), atol=1e-4)
        # Same neighbours (ties at equal distance may swap places)
        assert set(c['customer_id'] for c in body['similar_customers']) == set(expected_ids) \
            or np.isclose(expected_d[-1], got_d[-1], atol=1e-4)


def test_similarity_score_is_derived_from_distance(client, sample_ids):
    for c in _similar(client, sample_ids[0], 50)['similar_customers']:
        assert c['similarity_score'] == round(100.0 / (1.0 + c['distance']), 1)
        assert 0 < c['similarity_score'] <= 100


def test_default_is_five_and_alias_route_is_identical(client, sample_ids):
    a = _similar(client, sample_ids[0])
    b = _similar(client, sample_ids[0], path='/customer-similarity')
    assert a == b and a['count'] == 5


def test_results_are_deterministic(client, sample_ids):
    assert _similar(client, sample_ids[1], 7) == _similar(client, sample_ids[1], 7)


def test_smaller_k_is_a_prefix_of_larger_k(client, sample_ids):
    for cid in sample_ids[:5]:
        big = [c['customer_id'] for c in _similar(client, cid, 20)['similar_customers']]
        small = [c['customer_id'] for c in _similar(client, cid, 5)['similar_customers']]
        assert small == big[:5]


# ── Normalisation and target-leakage protections are preserved ───────────────
def test_feature_space_is_standardised_and_excludes_leakage_columns(api):
    engine = api[0].SIMILARITY_ENGINE
    used = set(cs.NUMERICAL_FEATURES) | set(cs.CATEGORICAL_FEATURES)
    for leak in ('churn', 'churn_probability', 'clv_score', 'clv_segment',
                 'customer_id', 'name', 'email', 'churn_prob', 'risk_level'):
        assert leak not in used
    scaler = engine.pipeline.named_transformers_['num'].named_steps['scaler']
    assert isinstance(scaler, StandardScaler)
    Xn = scaler.transform(engine.pipeline.named_transformers_['num'].named_steps['imputer']
                          .transform(engine._prepare_dataframe(api[0].DATASET_DF)[cs.NUMERICAL_FEATURES]))
    np.testing.assert_allclose(Xn.mean(axis=0), 0, atol=1e-6)
    np.testing.assert_allclose(Xn.std(axis=0), 1, atol=1e-6)


def test_target_and_prediction_columns_do_not_affect_neighbours(api, client, monkeypatch, sample_ids):
    main = api[0]
    before = _similar(client, sample_ids[0], 10)
    df = main.FULL_DF.copy()
    rng = np.random.RandomState(0)
    df['churn_probability'] = rng.rand(len(df))     # scramble the generator oracle
    df['churn_prob'] = rng.rand(len(df))            # and the model output
    monkeypatch.setattr(main, 'FULL_DF', df)
    after = _similar(client, sample_ids[0], 10)
    key = lambda b: [(c['customer_id'], c['distance']) for c in b['similar_customers']]
    assert key(before) == key(after)


# ── Values shown for neighbours ──────────────────────────────────────────────
def test_historical_outcome_is_the_dataset_label(api, client, sample_ids):
    labels = api[0].DATASET_DF.set_index('customer_id')['churn']
    for c in _similar(client, sample_ids[0], 50)['similar_customers']:
        assert c['historical_churn'] == int(labels[c['customer_id']])
        assert c['historical_outcome'] == ('Churned' if c['historical_churn'] else 'Retained')


def test_neighbour_probabilities_are_model_predictions_not_generator_values(api, client, sample_ids):
    preds = api[0].PREDICTIONS_DF.set_index('customer_id')['churn_prob']
    oracle = api[0].DATASET_DF.set_index('customer_id')['churn_probability']
    nb = _similar(client, sample_ids[0], 50)['similar_customers']
    for c in nb:
        assert c['churn_prob'] == round(float(preds[c['customer_id']]), 4)
    assert sum(c['churn_prob'] == round(float(oracle[c['customer_id']]), 4) for c in nb) < 3


def test_unscored_neighbour_is_reported_not_scored(api, client, monkeypatch, sample_ids):
    main = api[0]
    first = _similar(client, sample_ids[0], 5)['similar_customers'][0]['customer_id']
    df = main.FULL_DF.copy()
    df.loc[df['customer_id'] == first, ['churn_prob', 'risk_level', 'clv_score']] = np.nan
    monkeypatch.setattr(main, 'FULL_DF', df)
    c = _similar(client, sample_ids[0], 5)['similar_customers'][0]
    assert c['customer_id'] == first
    assert c['churn_prob'] is None and c['risk_level'] == 'NOT_SCORED'
    assert c['churn_percent'] == 'Not scored'


def test_insights_agree_with_returned_neighbours(client, sample_ids):
    body = _similar(client, sample_ids[0], 10)
    churned = sum(c['historical_churn'] == 1 for c in body['similar_customers'])
    first = body['insights'][0]
    if churned:
        assert first.startswith(f'{churned} of the 10 most similar')
    else:
        assert first.startswith('All 10 similar historical customers')


# ── Engine-level edge cases ──────────────────────────────────────────────────
@pytest.fixture(scope='module')
def tiny_engine(api, tmp_path_factory):
    df = api[0].DATASET_DF.head(8).copy()
    engine = CustomerSimilarityEngine(artifacts_dir=str(tmp_path_factory.mktemp('sim')))
    engine.fit(df)
    return engine, df


def test_engine_returns_everyone_else_when_k_exceeds_dataset(tiny_engine):
    engine, df = tiny_engine
    res = engine.find_similar_customers(df['customer_id'].iloc[0], n_neighbors=50, full_df=df)
    assert res['count'] == len(df) - 1
    assert df['customer_id'].iloc[0] not in [c['customer_id'] for c in res['similar_customers']]


@pytest.mark.parametrize('bad', [0, -1, 2.5, '3', None, True])
def test_engine_rejects_invalid_k(tiny_engine, bad):
    engine, df = tiny_engine
    with pytest.raises(ValueError):
        engine.find_similar_customers(df['customer_id'].iloc[0], n_neighbors=bad, full_df=df)


def test_engine_unknown_customer_raises_key_error(tiny_engine):
    engine, df = tiny_engine
    with pytest.raises(KeyError):
        engine.find_similar_customers('CUST_NOPE', n_neighbors=3, full_df=df)


def test_unfitted_engine_raises_value_error():
    with pytest.raises(ValueError):
        CustomerSimilarityEngine().find_similar_customers('CUST00001')


def test_engine_save_and_load_round_trip(tiny_engine, tmp_path):
    engine, df = tiny_engine
    engine.save(str(tmp_path))
    loaded = CustomerSimilarityEngine()
    assert loaded.load(str(tmp_path), data_df=df)
    cid = df['customer_id'].iloc[3]
    assert loaded.find_similar_customers(cid, 4, full_df=df) == \
        engine.find_similar_customers(cid, 4, full_df=df)
    assert CustomerSimilarityEngine().load(str(tmp_path / 'missing')) is False
