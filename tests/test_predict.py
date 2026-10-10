import os
import pytest
from fastapi.testclient import TestClient
from app.main import app

valid_payload = {
    "order_id": "TEST1",
    "customer_id": "C-12345",
    "sku": "SKU-9999",
    "order_placed_at": "2026-05-15 10:00:00",
    "payment_mode": "cod",
    "sales_channel": "website",
    "discount_pct": 10.0,
    "qty": 1,
    "order_value_inr": 2500.0,
    "promised_delivery_days": 3,
    "delivery_pincode": "400001",
    "delivery_note": "",
    "is_gift": "N",
    "customer_prior_orders": 2,
    "customer_prior_returns": 0
}

def test_valid_order_and_unknown_sku():
    with TestClient(app) as client:
        response = client.post("/predict", json=valid_payload)
        assert response.status_code == 200, response.json()
        data = response.json()
        assert "score" in data
        assert "risk_band" in data
        assert "recommended_action" in data
        assert "expected_saving_inr" in data
        assert "reasons" in data
        assert "warnings" in data
        assert any("Unknown SKU" in w for w in data["warnings"])
        assert any("customer not found; history assumed empty" in w for w in data["warnings"])

def test_missing_field():
    with TestClient(app) as client:
        payload = valid_payload.copy()
        del payload["payment_mode"]
        response = client.post("/predict", json=payload)
        assert response.status_code == 400

def test_leaky_fields_ignored():
    with TestClient(app) as client:
        payload = valid_payload.copy()
        payload["last_service_event_type"] = "REPAIR"
        payload["pickup_scheduled_at"] = "2026-05-18"
        response = client.post("/predict", json=payload)
        assert response.status_code == 200
        warnings = response.json().get("warnings", [])
        assert any("ignored" in w.lower() for w in warnings)

def test_october_repair():
    with TestClient(app) as client:
        payload = valid_payload.copy()
        payload["order_placed_at"] = "2025-10-15 10:00:00"
        payload["order_value_inr"] = 250000.0 # x100 error
        response = client.post("/predict", json=payload)
        assert response.status_code == 200
        warnings = response.json().get("warnings", [])
        assert any("October" in w for w in warnings)

def test_shield_never_hold_review():
    with TestClient(app) as client:
        import pandas as pd
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        df_cust = pd.read_csv(os.path.join(base_dir, "data", "customers.csv"))
        shield_cust = df_cust[df_cust["shield_member"] == "Y"].iloc[0]["customer_id"]
        
        payload = valid_payload.copy()
        payload["customer_id"] = shield_cust
        payload["payment_mode"] = "cod"
        payload["customer_prior_returns"] = 10
        
        response = client.post("/predict", json=payload)
        assert response.status_code == 200
        data = response.json()
        
        # Action shouldn't be hold_review
        assert data["recommended_action"] != "hold_review"
        assert "hold" not in data["recommended_action"]
        assert "review_options" not in data or "hold_review" not in data["review_options"]
        
        # Test the action ranges
        # High risk shield -> call (high priority)
        if data["score"] >= 0.25:
            assert data["recommended_action"] == "call (high priority)"
            
def test_samples_endpoint():
    with TestClient(app) as client:
        response = client.get("/samples")
        assert response.status_code == 200
        data = response.json()
        assert "high" in data
        assert "low" in data
        assert "shield" in data
