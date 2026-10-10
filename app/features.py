import pandas as pd
import numpy as np

# Canonical feature list for the model (ensures order is identical for API)
FEATURE_COLUMNS = [
    # Numerical
    "discount_pct", "qty", "promised_delivery_days", 
    "customer_prior_orders", "customer_prior_returns", "prior_return_rate",
    "customer_tenure_days", "log_order_value", "log_list_price",
    "warranty_months", "order_hour", "order_weekday",
    
    # Binary flags
    "is_no_address", "has_note", "note_mentions_call", 
    "is_gift_Y", "shield_member_Y",
    
    # Payment mode (baseline: prepaid_card)
    "pay_cod", "pay_emi", "pay_prepaid_upi",
    
    # Sales channel (baseline: web)
    "chan_app", "chan_marketplace", "chan_partner_outlet",
    
    # Product family (baseline: Ceiling Fan)
    "fam_Air_Fryer", "fam_Induction_Cooktop", "fam_Mixer_Grinder", 
    "fam_Robot_Vacuum", "fam_Room_Heater", "fam_Water_Purifier"
]

def prep_data(df_orders, df_customers, df_products, is_train=False):
    """
    Cleans data and engineers features.
    If is_train=True, deduplicates on order_id and returns (X, df_clean).
    Otherwise returns just X (for API/test set).
    """
    df = df_orders.copy()
    
    # 1. Deduplicate (only relevant for train, per D-01)
    if is_train and "source" in df.columns:
        # Keep 'crm' source, drop 'partner_feed'
        df = df[df["source"] == "crm"].drop_duplicates(subset=["order_id"])
        
    # Join reference data
    df = df.merge(df_customers, on="customer_id", how="left")
    df = df.merge(df_products, on="sku", how="left")
    
    # Convert dates
    df["order_placed_at"] = pd.to_datetime(df["order_placed_at"])
    if "signup_date" in df.columns:
        df["signup_date"] = pd.to_datetime(df["signup_date"])
        
    # 2. Fix October 2025 anomaly (D-02)
    is_oct_2025 = (df["order_placed_at"].dt.year == 2025) & (df["order_placed_at"].dt.month == 10)
    df.loc[is_oct_2025, "order_value_inr"] = df.loc[is_oct_2025, "order_value_inr"] / 100.0

    # 3. Pincode as missing/placeholder (D-03)
    df["is_no_address"] = (df["delivery_pincode"] == "000000").astype(int)
    
    # Feature Engineering
    df["customer_tenure_days"] = (df["order_placed_at"] - df["signup_date"]).dt.days.fillna(0)
    df["order_hour"] = df["order_placed_at"].dt.hour
    df["order_weekday"] = df["order_placed_at"].dt.weekday
    
    df["has_note"] = df["delivery_note"].notna().astype(int)
    df["note_mentions_call"] = df["delivery_note"].fillna("").str.lower().str.contains("call").astype(int)
    
    df["log_order_value"] = np.log1p(df["order_value_inr"].fillna(0))
    df["log_list_price"] = np.log1p(df["list_price_inr"].fillna(0))
    
    df["prior_return_rate"] = df["customer_prior_returns"] / (df["customer_prior_orders"] + 1)
    
    # Binary categoricals
    df["is_gift_Y"] = (df["is_gift"] == "Y").astype(int)
    df["shield_member_Y"] = (df["shield_member"] == "Y").astype(int)
    
    # One-hot encoding (manual to ensure fixed columns for API)
    df["pay_cod"] = (df["payment_mode"] == "cod").astype(int)
    df["pay_emi"] = (df["payment_mode"] == "emi").astype(int)
    df["pay_prepaid_upi"] = (df["payment_mode"] == "prepaid_upi").astype(int)
    # prepaid_card is baseline
    
    df["chan_app"] = (df["sales_channel"] == "app").astype(int)
    df["chan_marketplace"] = (df["sales_channel"] == "marketplace").astype(int)
    df["chan_partner_outlet"] = (df["sales_channel"] == "partner_outlet").astype(int)
    # web is baseline
    
    df["fam_Air_Fryer"] = (df["family"] == "Air Fryer").astype(int)
    df["fam_Induction_Cooktop"] = (df["family"] == "Induction Cooktop").astype(int)
    df["fam_Mixer_Grinder"] = (df["family"] == "Mixer Grinder").astype(int)
    df["fam_Robot_Vacuum"] = (df["family"] == "Robot Vacuum").astype(int)
    df["fam_Room_Heater"] = (df["family"] == "Room Heater").astype(int)
    df["fam_Water_Purifier"] = (df["family"] == "Water Purifier").astype(int)
    # Ceiling Fan is baseline
    
    # Assemble X
    X = df[FEATURE_COLUMNS].copy()
    X = X.fillna(0)
    
    if is_train:
        return X, df
    return X
