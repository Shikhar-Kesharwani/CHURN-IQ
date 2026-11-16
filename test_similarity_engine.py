import os
import sys
import pandas as pd
from customer_similarity import CustomerSimilarityEngine

def test_engine():
    print("=== Testing CustomerSimilarityEngine ===")
    dataset_path = "ott_churn_dataset.csv"
    if not os.path.exists(dataset_path):
        print(f"Error: {dataset_path} not found")
        sys.exit(1)

    df = pd.read_csv(dataset_path)
    print(f"Loaded dataset with {len(df)} rows.")

    engine = CustomerSimilarityEngine(data_df=df)
    engine.fit(df)
    engine.save()

    print("Verifying artifacts exist on disk...")
    for f in ["customer_similarity_model.joblib", "similarity_pipeline.joblib", "similarity_metadata.joblib"]:
        assert os.path.exists(f), f"Missing artifact {f}"
        print(f"  Artifact {f}: {os.path.getsize(f)} bytes")

    # Test loading from disk
    loaded_engine = CustomerSimilarityEngine()
    success = loaded_engine.load(data_df=df)
    assert success, "Engine failed to load from disk"
    print("Loaded engine successfully from disk.")

    # Test query for CUST00001
    test_id = "CUST00001"
    res = loaded_engine.find_similar_customers(test_id, n_neighbors=5, full_df=df)

    assert "selected_customer" in res, "Missing selected_customer in result"
    assert "similar_customers" in res, "Missing similar_customers in result"
    assert "insights" in res, "Missing insights in result"

    assert res["selected_customer"]["customer_id"] == test_id
    similar = res["similar_customers"]
    print(f"Number of similar customers returned: {len(similar)}")
    assert len(similar) == 5, f"Expected 5 neighbors, got {len(similar)}"

    # Verify selected customer is excluded
    neighbor_ids = [c["customer_id"] for c in similar]
    print(f"Neighbor IDs: {neighbor_ids}")
    assert test_id not in neighbor_ids, f"Selected customer {test_id} was not excluded from neighbors!"

    # Verify descending similarity order
    sim_scores = [c["similarity_score"] for c in similar]
    print(f"Similarity scores: {sim_scores}")
    for i in range(len(sim_scores) - 1):
        assert sim_scores[i] >= sim_scores[i + 1], f"Similarity scores not sorted descending: {sim_scores}"

    # Verify distance ascending order
    distances = [c["distance"] for c in similar]
    print(f"Distances: {distances}")
    for i in range(len(distances) - 1):
        assert distances[i] <= distances[i + 1], f"Distances not sorted ascending: {distances}"

    # Verify historical outcomes
    for c in similar:
        assert c["historical_churn"] in (0, 1), f"Invalid historical churn: {c['historical_churn']}"
        assert c["historical_outcome"] in ("Retained", "Churned"), f"Invalid outcome string: {c['historical_outcome']}"
        assert 0.0 <= c["similarity_score"] <= 100.0, f"Similarity score out of bounds: {c['similarity_score']}"

    # Verify insights
    print("\nGenerated Insights:")
    for ins in res["insights"]:
        print(f"  - {ins}")
    assert len(res["insights"]) > 0, "No insights generated"

    # Test non-existent customer
    try:
        loaded_engine.find_similar_customers("INVALID_ID_999", n_neighbors=5, full_df=df)
        assert False, "Should have raised KeyError for invalid customer ID"
    except KeyError:
        print("\nVerified KeyError correctly raised for invalid customer ID.")

    print("\n✓ ALL CUSTOMER SIMILARITY ENGINE TESTS PASSED!")

if __name__ == "__main__":
    test_engine()
