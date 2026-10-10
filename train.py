import os
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
import sys
import io
import json
import joblib
from joblib import parallel_backend
import pandas as pd
import numpy as np
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score, average_precision_score, accuracy_score
from sklearn.calibration import calibration_curve
from app.features import prep_data, FEATURE_COLUMNS

# ── Dual-output: write to both stdout and a file ───────────────────────────
os.makedirs("evidence", exist_ok=True)
os.makedirs("model", exist_ok=True)
_file_out = open("evidence/train_output.txt", "w", encoding="utf-8")
_orig_stdout = sys.stdout

class Tee:
    def __init__(self, *streams):
        self.streams = streams
    def write(self, data):
        for s in self.streams:
            s.write(data)
    def flush(self):
        for s in self.streams:
            s.flush()

sys.stdout = Tee(io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8"), _file_out)

print("Kestrel Returns - Model Training")
print("="*60)

# ── Excluded Columns ───────────────────────────────────────────────────────
print("EXCLUDED COLUMNS & REASONS:")
excluded = {
    "last_service_event_type": "Leakage: captured after outcome (D-04)",
    "pickup_scheduled_at": "Leakage: filled only after return approved (D-05)",
    "source": "Zero variance after dedup (D-06)",
    "delivery_pincode": "Categorical with missing placeholder '000000', replaced with is_no_address flag (D-07)",
    "delivery_note": "Free text, replaced with has_note and note_mentions_call flags (D-08)",
    "order_id": "Identifier",
    "customer_id": "Identifier",
    "sku": "Identifier",
    "order_placed_at": "Used for split, time features extracted",
    "returned": "Target variable"
}
for col, reason in excluded.items():
    print(f"- {col}: {reason}")
print()
print(f"FEATURES KEPT ({len(FEATURE_COLUMNS)} columns):")
print(", ".join(FEATURE_COLUMNS))
print("="*60)

# ── Load Data ─────────────────────────────────────────────────────────────
df_train_raw = pd.read_csv("data/train.csv", dtype={"delivery_pincode": str})
df_cust = pd.read_csv("data/customers.csv")
df_prod = pd.read_csv("data/products.csv")

X_all, df_clean = prep_data(df_train_raw, df_cust, df_prod, is_train=True)
y_all = df_clean["returned"].values
df_clean["order_placed_at"] = pd.to_datetime(df_clean["order_placed_at"])

# ── Define Folds ─────────────────────────────────────────────────────────
folds = [
    {
        "name": "Fold 1 (Oct-Dec 2025)",
        "train_end": pd.Timestamp("2025-10-01"),
        "test_start": pd.Timestamp("2025-10-01"),
        "test_end": pd.Timestamp("2025-12-31 23:59:59")
    },
    {
        "name": "Fold 2 (Jan-Mar 2026)",
        "train_end": pd.Timestamp("2026-01-01"),
        "test_start": pd.Timestamp("2026-01-01"),
        "test_end": pd.Timestamp("2026-03-31 23:59:59")
    },
    {
        "name": "Fold 3 (Apr-Jun 2026)",
        "train_end": pd.Timestamp("2026-04-01"),
        "test_start": pd.Timestamp("2026-04-01"),
        "test_end": pd.Timestamp("2026-06-30 23:59:59")
    }
]

# ── Define Models ────────────────────────────────────────────────────────
models = {
    "Logistic Regression": Pipeline([
        ("scaler", StandardScaler()),
        ("lr", LogisticRegression(C=1.0, max_iter=1000, random_state=42))
    ]),
    "HistGradientBoosting": HistGradientBoostingClassifier(random_state=42)
}

results = []

for fold in folds:
    print(f"\n{fold['name']}")
    
    train_mask = df_clean["order_placed_at"] < fold["train_end"]
    test_mask = (df_clean["order_placed_at"] >= fold["test_start"]) & (df_clean["order_placed_at"] <= fold["test_end"])
    
    X_train, y_train = X_all[train_mask], y_all[train_mask]
    X_test, y_test = X_all[test_mask], y_all[test_mask]
    
    print(f"Train rows: {len(X_train)}, Test rows: {len(X_test)}")
    
    # COD Baseline
    cod_preds = X_test["pay_cod"] * 0.188 # baseline COD rate
    auc_cod = roc_auc_score(y_test, cod_preds)
    ap_cod = average_precision_score(y_test, cod_preds)
    print(f"  COD Baseline -> AUC: {auc_cod:.4f} | AP: {ap_cod:.4f}")

    fold_res = {"fold": fold["name"], "COD_auc": auc_cod, "COD_ap": ap_cod}
    
    with parallel_backend('sequential'):
        for m_name, model in models.items():
            model.fit(X_train, y_train)
            preds = model.predict_proba(X_test)[:, 1]
            auc = roc_auc_score(y_test, preds)
            ap = average_precision_score(y_test, preds)
            print(f"  {m_name:<20} -> AUC: {auc:.4f} | AP: {ap:.4f}")
            
            fold_res[f"{m_name}_auc"] = auc
            fold_res[f"{m_name}_ap"] = ap
            fold_res[f"{m_name}_preds"] = preds
        
    results.append(fold_res)
    
print("\n" + "="*60)
# ── Model Selection ─────────────────────────────────────────────────────
f3 = results[-1]
lr_auc = f3["Logistic Regression_auc"]
hgb_auc = f3["HistGradientBoosting_auc"]
diff = hgb_auc - lr_auc

if diff < 0:
    chosen_model_name = "Logistic Regression"
    reason = f"HistGradientBoosting scored {-diff:.4f} AUC LOWER than Logistic Regression. LR is simpler, easily explainable, and less prone to edge-case extrapolation."
elif diff < 0.01:
    chosen_model_name = "Logistic Regression"
    reason = f"HistGradientBoosting beats Logistic Regression by only {diff:.4f} AUC on the holdout (< 0.01). LR is simpler, easily explainable, and less prone to edge-case extrapolation."
else:
    chosen_model_name = "HistGradientBoosting"
    reason = f"HistGradientBoosting beats Logistic Regression by {diff:.4f} AUC (>= 0.01), providing enough uplift to justify the added complexity."

print(f"CHOSEN MODEL: {chosen_model_name}")
print(f"REASON: {reason}")

# ── Calibration Table for Chosen Model (Fold 3) ──────────────────────────
print("\nCALIBRATION (Fold 3) - Quintiles")
preds = f3[f"{chosen_model_name}_preds"]
y_test = y_all[(df_clean["order_placed_at"] >= folds[-1]["test_start"]) & (df_clean["order_placed_at"] <= folds[-1]["test_end"])]

df_cal = pd.DataFrame({"y_true": y_test, "y_pred": preds})
df_cal["quintile"] = pd.qcut(df_cal["y_pred"], q=5, labels=False)
cal_tbl = df_cal.groupby("quintile").agg(
    mean_pred=("y_pred", "mean"),
    actual_rate=("y_true", "mean"),
    count=("y_true", "count")
)
print(cal_tbl.to_string())

# ── Leakage Experiment ───────────────────────────────────────────────────
print("\n" + "="*60)
print("LEAKAGE EXPERIMENT (Fold 3)")
X_leaky = X_all.copy()
X_leaky["leaky_REVERSE_PICKUP"] = (df_clean.get("last_service_event_type", "") == "REVERSE_PICKUP").astype(int)
X_leaky["leaky_TECH_VISIT"] = (df_clean.get("last_service_event_type", "") == "TECH_VISIT").astype(int)
X_leaky["leaky_DEMO_DONE"] = (df_clean.get("last_service_event_type", "") == "DEMO_DONE").astype(int)
X_leaky["leaky_INSTALL_DONE"] = (df_clean.get("last_service_event_type", "") == "INSTALL_DONE").astype(int)
X_leaky["leaky_has_pickup"] = df_clean.get("pickup_scheduled_at").notna().astype(int)
y_leaky = y_all

train_mask = df_clean["order_placed_at"] < folds[-1]["train_end"]
test_mask = (df_clean["order_placed_at"] >= folds[-1]["test_start"]) & (df_clean["order_placed_at"] <= folds[-1]["test_end"])

X_train_l, y_train_l = X_leaky[train_mask], y_leaky[train_mask]
X_test_l, y_test_l = X_leaky[test_mask], y_leaky[test_mask]

leak_model = Pipeline([
    ("scaler", StandardScaler()),
    ("lr", LogisticRegression(C=1.0, max_iter=1000, random_state=42))
]) if chosen_model_name == "Logistic Regression" else HistGradientBoostingClassifier(random_state=42)

leak_model.fit(X_train_l, y_train_l)
preds_l_prob = leak_model.predict_proba(X_test_l)[:, 1]
preds_l_class = leak_model.predict(X_test_l)

auc_l = roc_auc_score(y_test_l, preds_l_prob)
acc_l = accuracy_score(y_test_l, preds_l_class)

honest_acc = accuracy_score(y_test, models[chosen_model_name].predict(X_test))

print(f"Honest Model ({chosen_model_name}) -> AUC: {f3[f'{chosen_model_name}_auc']:.4f} | Accuracy: {honest_acc:.4f}")
print(f"Leaky Model  ({chosen_model_name}) -> AUC: {auc_l:.4f} | Accuracy: {acc_l:.4f}")

# ── Final Fit & Save ─────────────────────────────────────────────────────
final_model = models[chosen_model_name]
final_model.fit(X_all, y_all)
joblib.dump(final_model, "model/model.joblib")

metrics = {
    "chosen_model": chosen_model_name,
    "fold3_auc": f3[f"{chosen_model_name}_auc"],
    "fold3_ap": f3[f"{chosen_model_name}_ap"],
    "leaky_auc": auc_l,
    "leaky_accuracy": acc_l
}
with open("evidence/metrics.json", "w") as f:
    json.dump(metrics, f, indent=2)

print("\nModel saved to model/model.joblib")
print("Metrics saved to evidence/metrics.json")
print("="*60)

sys.stdout = _orig_stdout
_file_out.close()
sys.exit(0)
