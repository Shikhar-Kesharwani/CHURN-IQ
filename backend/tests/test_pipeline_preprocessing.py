"""CHURN-13 — XGBoost pipeline review: preprocessing, leakage, SMOTE, reproducibility."""
import numpy as np
import pandas as pd
import pytest

import churniq_core as core
import churniq_ml_pipeline as pipeline


def test_encoded_columns_match_committed_feature_names(artifacts):
    assert list(artifacts['X'].columns) == list(artifacts['feature_names'])
    assert list(artifacts['model'].get_booster().feature_names) == list(artifacts['feature_names'])


def test_no_identifier_leakage_or_target_columns_in_features(artifacts):
    cols = set(artifacts['X'].columns)
    for c in core.ID_COLS + core.LEAKAGE_COLS + [core.TARGET_COL]:
        assert c not in cols


def test_single_row_encoding_equals_batch_encoding(artifacts):
    """Regression for the training/serving skew bug (single-row get_dummies)."""
    base, X, names = artifacts['base'], artifacts['X'], artifacts['feature_names']
    for i in range(0, len(base), 50):
        row = core.encode_features(base.iloc[[i]], names).astype(float).values[0]
        np.testing.assert_array_equal(row, X.iloc[i].astype(float).values)


def test_api_build_feature_row_matches_training_encoding(api, artifacts):
    main, _ = api
    base, X = artifacts['base'], artifacts['X']
    for i in range(0, len(base), 100):
        live = main.build_feature_row(base.iloc[i].to_dict()).astype(float).values[0]
        np.testing.assert_array_equal(live, X.iloc[i].astype(float).values)


def test_one_hot_columns_are_not_all_zero_at_serving_time(api, artifacts):
    main, _ = api
    row = artifacts['base'][artifacts['base']['device_type'] == 'Mobile'].iloc[0].to_dict()
    assert main.build_feature_row(row)['device_type_Mobile'].iloc[0] == 1


def test_noop_whatif_returns_original_probability(api, scored_ids):
    _, client = api
    for cid in scored_ids[::25]:
        r = client.post('/whatif', json={'customer_id': cid}).json()
        assert abs(r['change']) <= 1e-3, (cid, r)
        assert r['original_risk'] == r['new_risk']


def test_whatif_response_format_unchanged(api, scored_ids):
    _, client = api
    r = client.post('/whatif', json={'customer_id': scored_ids[0], 'payment_failures_3m': 0})
    assert r.status_code == 200
    assert set(r.json()) == {'customer_id', 'original_churn_prob', 'new_churn_prob', 'change',
                             'change_percent', 'original_risk', 'new_risk', 'improved'}


def test_unknown_category_level_encodes_as_baseline():
    row = pd.DataFrame([{'age': 30, 'gender': 'Unknown', 'country': 'Mars', 'plan_type': 'Basic',
                         'monthly_charge': 199, 'tenure_months': 5, 'watch_hours_per_week': 2.0,
                         'num_profiles': 1, 'logins_last_30_days': 3, 'last_login_days_ago': 2,
                         'preferred_genre': 'Action', 'device_type': 'Laptop',
                         'payment_method': 'Credit Card', 'payment_failures_3m': 0,
                         'support_tickets': 0}])
    enc = core.encode_features(row)
    assert not enc.filter(like='gender_').any(axis=None)
    assert not enc.filter(like='country_').any(axis=None)


def test_split_is_disjoint_stratified_and_matches_stored_predictions(artifacts):
    X_train, X_test = artifacts['X_train'], artifacts['X_test']
    assert set(X_train.index).isdisjoint(X_test.index)
    assert len(X_train) == 4000 and len(X_test) == 1000
    assert abs(artifacts['y_train'].mean() - artifacts['y_test'].mean()) < 0.005
    test_ids = set(artifacts['base'].loc[X_test.index, 'customer_id'])
    preds = artifacts['predictions']
    stored = set(preds.loc[preds['prediction_source'] == 'holdout_test', 'customer_id'])
    assert test_ids == stored


def test_smote_only_touches_training_data(artifacts):
    X_train, y_train, X_test = artifacts['X_train'], artifacts['y_train'], artifacts['X_test']
    X_sm, y_sm = pipeline.apply_smote(X_train, y_train)
    assert (y_sm == 0).sum() == (y_sm == 1).sum() == (y_train == 0).sum()
    # The original training rows are preserved and come first
    pd.testing.assert_frame_equal(X_sm.iloc[:len(X_train)].reset_index(drop=True),
                                  X_train.reset_index(drop=True))
    # No test row appears in the resampled training data
    test_rows = set(map(tuple, X_test.astype(float).values.round(6)))
    sm_rows = set(map(tuple, X_sm.astype(float).values.round(6)))
    assert test_rows.isdisjoint(sm_rows)


def test_demo_customer_excluded_from_training_matrix(artifacts):
    X, _ = pipeline.preprocess(artifacts['dataset'])
    assert len(X) == 5000


def test_dataset_generation_is_reproducible(artifacts):
    gen = pipeline.generate_dataset(with_names=False)
    committed = artifacts['base'].reset_index(drop=True)
    cols = [c for c in gen.columns if c != 'name']
    pd.testing.assert_frame_equal(gen[cols], committed[cols], check_dtype=False)


def test_training_is_deterministic(artifacts):
    params = dict(pipeline.XGB_PARAMS, n_estimators=20)
    X_sm, y_sm = pipeline.apply_smote(artifacts['X_train'], artifacts['y_train'])
    p1 = pipeline.train_model(X_sm, y_sm, params).predict_proba(artifacts['X_test'])[:, 1]
    p2 = pipeline.train_model(X_sm, y_sm, params).predict_proba(artifacts['X_test'])[:, 1]
    np.testing.assert_array_equal(p1, p2)


def test_committed_model_reproduces_stored_predictions(artifacts):
    prob = artifacts['model'].predict_proba(artifacts['X_test'])[:, 1]
    ids = artifacts['base'].loc[artifacts['X_test'].index, 'customer_id']
    stored = artifacts['predictions'].set_index('customer_id').loc[ids, 'churn_prob'].values
    assert np.abs(prob - stored).max() <= 1e-4
