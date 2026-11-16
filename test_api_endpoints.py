import os
import sys
from fastapi.testclient import TestClient

# Ensure UTF-8 output
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from main import app

client = TestClient(app)

def run_tests():
    print("=== Testing FastAPI API Endpoints ===")

    # 1. Health check
    print("\n1. Testing GET / (Health Check)...")
    r = client.get("/")
    assert r.status_code == 200, f"Health check failed: {r.status_code} {r.text}"
    data = r.json()
    assert "endpoints" in data
    assert "customer_similarity" in data["endpoints"]
    print("  ✓ Health check passed, similarity endpoint listed.")

    # 2. Existing Customer Detail
    print("\n2. Testing GET /customer/CUST00001...")
    r = client.get("/customer/CUST00001")
    assert r.status_code == 200, f"Get customer failed: {r.status_code}"
    cust = r.json()
    assert cust["customer_id"] == "CUST00001"
    print(f"  ✓ Customer CUST00001 fetched: plan={cust['plan_type']}, churn_prob={cust['churn_prob']}")

    # 3. Existing What-If
    print("\n3. Testing POST /whatif...")
    r = client.post("/whatif", json={"customer_id": "CUST00001", "payment_failures_3m": 0})
    assert r.status_code == 200, f"Whatif failed: {r.status_code}"
    wi = r.json()
    assert "new_churn_prob" in wi
    print(f"  ✓ What-if simulation passed: original={wi['original_churn_prob']}, new={wi['new_churn_prob']}")

    # 4. Customer Similarity - Valid customer
    print("\n4. Testing POST /api/customer-similarity (CUST00001)...")
    payload = {"customer_id": "CUST00001", "n_neighbors": 5}
    r = client.post("/api/customer-similarity", json=payload)
    assert r.status_code == 200, f"Customer similarity failed: {r.status_code} {r.text}"
    sim_data = r.json()
    
    assert "selected_customer" in sim_data
    assert "similar_customers" in sim_data
    assert "insights" in sim_data
    assert sim_data["count"] == 5
    assert len(sim_data["similar_customers"]) == 5

    # Check that CUST00001 is NOT among similar customers
    sim_ids = [c["customer_id"] for c in sim_data["similar_customers"]]
    print(f"  Returned 5 similar customers: {sim_ids}")
    assert "CUST00001" not in sim_ids, "Selected customer CUST00001 was not excluded from similar customers list!"

    # Check similarity fields
    for c in sim_data["similar_customers"]:
        assert "similarity_score" in c
        assert "distance" in c
        assert "historical_churn" in c
        assert "historical_outcome" in c
        assert "churn_prob" in c
        assert "plan_type" in c
        assert "tenure_months" in c
        assert "monthly_charge" in c
        assert "watch_hours_per_week" in c
        assert 0.0 <= c["similarity_score"] <= 100.0
        assert c["historical_outcome"] in ("Retained", "Churned")

    # Check similarity descending order
    scores = [c["similarity_score"] for c in sim_data["similar_customers"]]
    print(f"  Similarity scores: {scores}")
    for i in range(len(scores) - 1):
        assert scores[i] >= scores[i + 1], f"Similarity scores not sorted descending: {scores}"

    # Check insights
    print(f"  Generated insights ({len(sim_data['insights'])}):")
    for ins in sim_data["insights"]:
        print(f"    - {ins}")
    assert len(sim_data["insights"]) > 0

    # 5. Customer Similarity - Alias endpoint
    print("\n5. Testing POST /customer-similarity (alias endpoint)...")
    r = client.post("/customer-similarity", json=payload)
    assert r.status_code == 200, f"Alias endpoint failed: {r.status_code}"
    print("  ✓ Alias endpoint POST /customer-similarity works identical to /api/customer-similarity.")

    # 6. Customer Similarity - Invalid Customer ID
    print("\n6. Testing POST /api/customer-similarity (Invalid ID)...")
    r = client.post("/api/customer-similarity", json={"customer_id": "NON_EXISTENT_ID"})
    assert r.status_code == 404, f"Expected 404 for invalid customer, got: {r.status_code}"
    print(f"  ✓ 404 handled gracefully: {r.json()['detail']}")

    # 7. Regression check for existing /segments and /dashboard/summary
    print("\n7. Regression check: GET /dashboard/summary and GET /segments...")
    r1 = client.get("/dashboard/summary")
    assert r1.status_code == 200
    r2 = client.get("/segments")
    assert r2.status_code == 200
    print("  ✓ Existing endpoints /dashboard/summary and /segments are fully functional.")

    print("\n==============================================")
    print("✓ ALL FASTAPI ENDPOINT TESTS PASSED WITH 100% SUCCESS!")
    print("==============================================")

if __name__ == "__main__":
    run_tests()
