import joblib
import pandas as pd
import numpy as np
from app.features import prep_data

# ── Load Model and Data ───────────────────────────────────────────────────
model = joblib.load("model/model.joblib")

df_test = pd.read_csv("data/test_unlabelled.csv", dtype={"delivery_pincode": str})
df_cust = pd.read_csv("data/customers.csv")
df_prod = pd.read_csv("data/products.csv")
df_sample = pd.read_csv("data/sample_submission.csv")

# ── Prepare Data ────────────────────────────────────────────────────────
X_test = prep_data(df_test, df_cust, df_prod, is_train=False)

# ── Predict ─────────────────────────────────────────────────────────────
scores = model.predict_proba(X_test)[:, 1]
df_test["score"] = scores

# ── Save predictions.csv ────────────────────────────────────────────────
# Ensure order matches sample_submission.csv exactly
df_out = df_test[["order_id", "score"]].copy()
df_out = pd.merge(df_sample[["order_id"]], df_out, on="order_id", how="left")
df_out.to_csv("predictions.csv", index=False)

# ── Assertions ──────────────────────────────────────────────────────────
import sys
with open("evidence/predictions_check.txt", "w") as f:
    f.write("Running Assertions on predictions.csv...\n")
    try:
        assert len(df_out) == 2096, f"Expected 2096 rows, got {len(df_out)}"
        assert df_out["order_id"].nunique() == 2096, "order_ids are not unique"
        assert list(df_out["order_id"]) == list(df_sample["order_id"]), "order_ids do not match sample_submission exactly"
        assert np.isfinite(df_out["score"]).all(), "Scores contain non-finite values"
        assert df_out["score"].isna().sum() == 0, "Scores contain NaN values"
        
        f.write("All assertions passed!\n")
        f.write(f"Row count: {len(df_out)}\n")
        f.write("IDs are unique and match sample_submission.\n")
        f.write("Scores are finite.\n")
    except AssertionError as e:
        f.write(f"Assertion failed: {e}\n")
        print(f"Assertion failed: {e}")
        sys.exit(1)

# ── Analysis for the user ───────────────────────────────────────────────
print("First 5 rows:")
print(df_out.head())

mean_score = df_out["score"].mean()
share_above_112 = (df_out["score"] > 0.112).mean()

# To get cod vs non-cod, we can look at X_test (assuming 'pay_cod' is available)
mean_cod = df_test.loc[X_test["pay_cod"] == 1, "score"].mean()
mean_non_cod = df_test.loc[X_test["pay_cod"] == 0, "score"].mean()

print(f"\nMean score: {mean_score:.4f}")
print(f"Share of orders above 0.112: {share_above_112:.2%}")
print(f"Mean score for COD orders: {mean_cod:.4f}")
print(f"Mean score for non-COD orders: {mean_non_cod:.4f}")
