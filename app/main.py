import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field
from typing import Optional, List
import joblib
import pandas as pd
import numpy as np
from app.features import prep_data, FEATURE_COLUMNS
import warnings

app = FastAPI(title="Kestrel Returns API", version="1.0")

# ── Global State ──────────────────────────────────────────────────────────
model = None
df_customers = None
df_products = None

@app.on_event("startup")
def load_assets():
    global model, df_customers, df_products
    # Use relative paths for app execution
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    model_path = os.path.join(base_dir, "model", "model.joblib")
    cust_path = os.path.join(base_dir, "data", "customers.csv")
    prod_path = os.path.join(base_dir, "data", "products.csv")
    
    if os.path.exists(model_path):
        model = joblib.load(model_path)
    if os.path.exists(cust_path):
        df_customers = pd.read_csv(cust_path)
    if os.path.exists(prod_path):
        df_products = pd.read_csv(prod_path)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    missing_fields = [f"{err['loc'][-1]}" for err in errors if err['type'] == 'value_error.missing' or 'missing' in err['type']]
    if not missing_fields:
        missing_fields = [f"{err['loc'][-1]}" for err in errors]
    return JSONResponse(
        status_code=400,
        content={"detail": f"Missing or invalid fields: {', '.join(missing_fields)}"}
    )

# ── Schemas ───────────────────────────────────────────────────────────────
class OrderRequest(BaseModel):
    order_id: Optional[str] = "test-123"
    customer_id: str
    sku: str
    order_placed_at: str
    payment_mode: str
    sales_channel: str
    discount_pct: float
    qty: int
    order_value_inr: float
    promised_delivery_days: int
    delivery_pincode: str
    delivery_note: Optional[str] = None
    is_gift: str
    customer_prior_orders: int
    customer_prior_returns: int
    shield_override: Optional[bool] = None   # manual override when customer not in CSV
    last_service_event_type: Optional[str] = None
    pickup_scheduled_at: Optional[str] = None

# ── Helpers ───────────────────────────────────────────────────────────────
def generate_reasons(X_scaled, X_raw):
    """
    Generates plain English reasons based on model coefficients and standardized feature values.
    """
    lr_model = model.named_steps['lr']
    
    # Calculate log-odds contribution of each feature
    contributions = lr_model.coef_[0] * X_scaled[0]
    
    feature_impacts = list(zip(FEATURE_COLUMNS, contributions))
    feature_impacts.sort(key=lambda x: x[1], reverse=True)
    
    reasons = []
    for feat, impact in feature_impacts:
        if impact > 0.1 and len(reasons) < 5:
            val = X_raw[feat].iloc[0]
            if feat == "pay_cod" and val == 1:
                reasons.append("Paid by cash on delivery. Orders like this are returned about twice as often.")
            elif feat == "prior_return_rate":
                reasons.append(f"This customer has a history of returning items.")
            elif feat == "prior_returns":
                reasons.append(f"This customer has returned {int(val)} earlier orders.")
            elif feat == "promised_delivery_days" and val > 5:
                reasons.append(f"Delivery promised in {int(val)} days; long waits raise returns.")
            elif feat == "log_order_value" or feat == "order_value_inr":
                reasons.append("This is a high-value order, which typically carries an elevated return risk.")
            elif feat == "is_no_address" and val == 1:
                reasons.append("The delivery pincode is missing or invalid, suggesting an incomplete address.")
            elif feat == "note_mentions_call" and val == 1:
                reasons.append("The delivery note specifically requests a phone call before delivery.")
            elif feat == "customer_tenure_days" and val < 30:
                reasons.append("This is a relatively new customer. Newer customers tend to have higher return rates.")
            elif feat == "discount_pct" and val > 20:
                reasons.append("A heavy discount was applied, which is often associated with higher returns.")
            elif "family" in feat and val == 1:
                category = feat.replace("family_", "").replace("_", " ").title()
                reasons.append(f"Orders in the {category} category tend to have higher return rates.")
                
    if not reasons:
        reasons.append("Multiple small factors combine to elevate the risk of this order.")
        
    return reasons[:5]

# ── Endpoints ─────────────────────────────────────────────────────────────
@app.get("/health")
def health_check():
    return {"status": "ok", "version": "1.0"}

@app.post("/predict")
def predict_risk(order: OrderRequest):
    global model, df_customers, df_products
    
    if model is None:
        raise HTTPException(status_code=503, detail="Model is missing. Please train the model and save it to model/model.joblib.")
        
    if df_customers is None or df_products is None:
        raise HTTPException(status_code=503, detail="reference data not found; copy the CSVs into data/")
        
    warnings_list = []
    
    # 1. Leaky fields check
    if order.last_service_event_type or order.pickup_scheduled_at:
        warnings_list.append("The fields last_service_event_type and pickup_scheduled_at are not used for predictions and were ignored.")
    order_dict = order.model_dump()
    order_dict.pop("last_service_event_type", None)
    order_dict.pop("pickup_scheduled_at", None)
    
    # 2. October value repair
    dt = pd.to_datetime(order_dict["order_placed_at"])
    if dt.year == 2025 and dt.month == 10:
        if order_dict["order_value_inr"] > 100000:
            order_dict["order_value_inr"] = order_dict["order_value_inr"] / 100.0
            warnings_list.append("Applied October x100 value repair to order_value_inr.")
            
    # 3. Reference lookups and Unknown SKU / Customer
    cust_id = order_dict["customer_id"]
    sku = order_dict["sku"]
    
    is_shield = False
    if df_customers is not None:
        cust_row = df_customers[df_customers["customer_id"] == cust_id]
        if cust_row.empty:
            # Customer not in reference data — fall back to manual checkbox if provided
            if order.shield_override:
                is_shield = True
                warnings_list.append("customer not found in CSV; Shield status taken from manual override checkbox.")
            else:
                warnings_list.append("customer not found; history assumed empty, risk may be understated")
        else:
            is_shield = (cust_row.iloc[0]["shield_member"] == "Y")
    else:
        if order.shield_override:
            is_shield = True
        warnings_list.append("customer not found; history assumed empty, risk may be understated")
    
    if df_products is not None:
        prod_row = df_products[df_products["sku"] == sku]
        if prod_row.empty:
            warnings_list.append(f"Unknown SKU '{sku}'. Falling back to default product values.")
            
    df_order = pd.DataFrame([order_dict])
    
    # Prep data
    try:
        X_raw = prep_data(df_order, df_customers, df_products, is_train=False)
        X_scaled = model.named_steps["scaler"].transform(X_raw)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error processing order data: {str(e)}")
        
    prob = model.named_steps["lr"].predict_proba(X_scaled)[0, 1]
    
    # Economics Logic
    # Top 10% threshold approx 0.25 (based on fold 3)
    # Break-even threshold 0.112
    if prob >= 0.25:
        risk_band = "HIGH"
        action = "call (high priority)"
    elif prob >= 0.112:
        risk_band = "MEDIUM"
        action = "call"
    else:
        risk_band = "LOW"
        action = "ship"
        
    expected_saving = 0.0
    if action in ["call", "call (high priority)"]:
        expected_saving = (prob * 0.35 * 1150) - 45
        
    # Offer hold only as an optional note ("hold would risk cancellations; see memo") and never for Shield members.
    if risk_band == "HIGH" and not is_shield:
        warnings_list.append("hold would risk cancellations; see memo")

    reasons = generate_reasons(X_scaled, X_raw)
    
    response = {
        "score": float(prob),
        "risk_band": risk_band,
        "recommended_action": action,
        "expected_saving_inr": round(float(expected_saving), 2),
        "reasons": reasons,
        "model_version": "1.0",
        "is_shield": is_shield
    }
        
    if warnings_list:
        response["warnings"] = warnings_list
        
    return response

@app.get("/samples")
def get_samples():
    path = os.path.join(os.path.dirname(__file__), "..", "data", "test_unlabelled.csv")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Data folder missing; manual entry required.")
        
    try:
        df_test = pd.read_csv(path)
        
        # Get specific known rows if they exist, otherwise fallback to first rows
        def get_row(order_id, default_idx):
            rows = df_test[df_test["order_id"] == order_id]
            row_s = rows.iloc[0] if not rows.empty else df_test.iloc[default_idx]
            # Drop unwanted columns
            for col in ["last_service_event_type", "pickup_scheduled_at", "source"]:
                if col in row_s:
                    row_s = row_s.drop(col)
            # Convert NaNs to None for JSON
            d = row_s.to_dict()
            return {k: (None if isinstance(v, float) and pd.isna(v) else v) for k, v in d.items()}

        return {
            "high": get_row("KO2610513", 0),
            "low": get_row("KO2610504", 1),
            "shield": get_row("KO2610509", 2)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading samples: {str(e)}")

# Serve static files for the screen
os.makedirs(os.path.join(os.path.dirname(__file__), "static"), exist_ok=True)
app.mount("/", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static"), html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
