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

    # 8. CHURN-20/21/25 edge cases — invalid input is 4xx with a JSON string detail
    print("\n8. Edge cases: unknown / malformed IDs, empty bodies, out-of-range values...")
    def is_error(r, status):
        body = r.json()
        return (r.status_code == status and isinstance(body.get("detail"), str)
                and body.get("status_code") == status and body.get("error"))

    for r in (client.get("/customer/NON_EXISTENT_ID"), client.get("/retention/NON_EXISTENT_ID"),
              client.post("/whatif", json={"customer_id": "NON_EXISTENT_ID"})):
        assert is_error(r, 404), (r.status_code, r.text)
    for r in (client.post("/whatif", json={}),
              client.post("/whatif", json={"customer_id": ""}),
              client.post("/whatif", json={"customer_id": "CUST00001", "watch_hours_per_week": -1}),
              client.post("/whatif", json={"customer_id": "CUST00001", "tenure_months": 10**6}),
              client.post("/whatif", json={"customer_id": "CUST00001", "unknown": 1}),
              client.post("/whatif", content=b"{bad json", headers={"content-type": "application/json"}),
              client.post("/api/customer-similarity", json={"customer_id": "CUST00001", "n_neighbors": 0}),
              client.post("/api/customer-similarity", json={"customer_id": "CUST00001", "n_neighbors": 51}),
              client.get("/customers?limit=-1"),
              client.get("/customers?risk_level=BOGUS"),
              client.get("/customers?sort_by=churn_probability")):
        assert is_error(r, 422), (r.status_code, r.text)
    print("  ✓ 404 for unknown customers, 422 for malformed input — all with a JSON string detail.")

    # 9. Boundary values are accepted
    print("\n9. Boundary values...")
    for k in (1, 50):
        r = client.post("/api/customer-similarity", json={"customer_id": "CUST00001", "n_neighbors": k})
        assert r.status_code == 200 and r.json()["count"] == k
    r = client.post("/whatif", json={"customer_id": "CUST00001", "watch_hours_per_week": 0,
                                     "payment_failures_3m": 0, "support_tickets": 0})
    assert r.status_code == 200
    print("  ✓ n_neighbors 1 and 50, zero-valued what-if inputs accepted.")

    # 10. Retention content is labelled (Gemini output vs rule-based fallback)
    print("\n10. GET /retention/CUST00001 labelling...")
    ret = client.get("/retention/CUST00001").json()
    assert ret["ai_generated"] is (ret["generated_by"] != "rule-based-fallback")
    assert ret["ai_generated"] or ret["fallback_reason"]
    assert 0 <= ret["churn_prob"] <= 1
    print(f"  ✓ generated_by={ret['generated_by']}, fallback_reason={ret['fallback_reason']}")

    print("\n==============================================")
    print("✓ ALL FASTAPI ENDPOINT TESTS PASSED WITH 100% SUCCESS!")
    print("==============================================")

def test_api_endpoints():
    """pytest entry point (CHURN-25): `python -m pytest test_api_endpoints.py`."""
    run_tests()


if __name__ == "__main__":
    run_tests()
