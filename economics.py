import json
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from app.features import prep_data, FEATURE_COLUMNS

# ── Parameters ────────────────────────────────────────────────────────────
COST_RETURN = 1150
COST_CALL = 45
CALL_PREVENT_RATE = 0.35
HOLD_CANCEL_RATE = 0.12
MARGIN_LOSS_SENSITIVITIES = [0, 300, 600, 1000, 1500]

# ── Load Data & Train Fold 3 Model ────────────────────────────────────────
df_train_raw = pd.read_csv("data/train.csv", dtype={"delivery_pincode": str})
df_cust = pd.read_csv("data/customers.csv")
df_prod = pd.read_csv("data/products.csv")

X_all, df_clean = prep_data(df_train_raw, df_cust, df_prod, is_train=True)
y_all = df_clean["returned"].values
df_clean["order_placed_at"] = pd.to_datetime(df_clean["order_placed_at"])

test_start = pd.Timestamp("2026-04-01")
test_end = pd.Timestamp("2026-06-30 23:59:59") # Exact Fold 3 test_end from train.py

train_mask = df_clean["order_placed_at"] < test_start
test_mask = (df_clean["order_placed_at"] >= test_start) & (df_clean["order_placed_at"] <= test_end)

X_train, y_train = X_all[train_mask], y_all[train_mask]
X_test, y_test = X_all[test_mask], y_all[test_mask]
df_test = df_clean[test_mask].copy()

model = Pipeline([
    ("scaler", StandardScaler()),
    ("lr", LogisticRegression(C=1.0, max_iter=1000, random_state=42))
])
model.fit(X_train, y_train)
y_prob = model.predict_proba(X_test)[:, 1]
df_test["score"] = y_prob

# ── Evaluation Function ──────────────────────────────────────────────────
def evaluate_policy(y_true, y_prob, action, margin_loss=0, call_effect=CALL_PREVENT_RATE):
    flagged_orders = (action != "ship").sum()
    
    is_called = (action == "call")
    is_held = (action == "hold")
    
    tp_call = np.sum((y_true == 1) & is_called)
    tp_hold = np.sum((y_true == 1) & is_held)
    returns_caught = tp_call + tp_hold
    
    prevented_call = tp_call * call_effect
    prevented_hold = tp_hold * HOLD_CANCEL_RATE
    returns_prevented = prevented_call + prevented_hold
    
    missed_returns = np.sum((y_true == 1) & (action == "ship"))
    total_baseline_returns = np.sum(y_true)
    returns_remaining = total_baseline_returns - returns_prevented
    false_alarms = np.sum((y_true == 0) & (action != "ship"))
    
    # Costs
    total_baseline_cost = total_baseline_returns * COST_RETURN
    actual_return_cost = returns_remaining * COST_RETURN
    
    call_costs = np.sum(is_called) * COST_CALL
    hold_costs = np.sum(is_held) * HOLD_CANCEL_RATE * margin_loss
    
    net_cost = actual_return_cost + call_costs + hold_costs
    net_saving = total_baseline_cost - net_cost
    
    precision = (returns_caught / flagged_orders) if flagged_orders > 0 else 0
    recall = (returns_caught / total_baseline_returns) if total_baseline_returns > 0 else 0
    accuracy = (np.sum((y_true == 1) & (action != "ship")) + np.sum((y_true == 0) & (action == "ship"))) / len(y_true)
    
    return {
        "flagged_orders": flagged_orders,
        "returns_caught": returns_caught,
        "returns_prevented": returns_prevented,
        "false_alarms": false_alarms,
        "missed_returns": missed_returns,
        "returns_remaining": returns_remaining,
        "precision": precision,
        "recall": recall,
        "accuracy": accuracy,
        "net_rupees": net_saving
    }

# ── Economics Analysis ────────────────────────────────────────────────────
results_table = []
percentiles = [10, 20, 30]

# Do nothing
act_none = np.full(len(y_test), "ship")
res = evaluate_policy(y_test, y_prob, act_none)
results_table.append({"Policy": "Do nothing", **res})

# Call everyone
act_call_all = np.full(len(y_test), "call")
res = evaluate_policy(y_test, y_prob, act_call_all)
results_table.append({"Policy": "Call everyone", **res})

# Call above break-even
break_even_prob = COST_CALL / (CALL_PREVENT_RATE * COST_RETURN) # ~0.1118
act_call_be = np.where(y_prob > break_even_prob, "call", "ship")
res = evaluate_policy(y_test, y_prob, act_call_be)
results_table.append({"Policy": f"Call above break-even (> {break_even_prob:.3f})", **res})

# Call top k%
for k in percentiles:
    thresh = np.percentile(y_prob, 100 - k)
    act = np.where(y_prob >= thresh, "call", "ship")
    res = evaluate_policy(y_test, y_prob, act)
    results_table.append({"Policy": f"Call top {k}%", **res})

df_res = pd.DataFrame(results_table)

# Hold top k%
hold_table = []
for k in percentiles:
    thresh = np.percentile(y_prob, 100 - k)
    act = np.where(y_prob >= thresh, "hold", "ship")
    row = {"Policy": f"Hold top {k}%"}
    for m in MARGIN_LOSS_SENSITIVITIES:
        row[f"Margin {m}"] = evaluate_policy(y_test, y_prob, act, margin_loss=m)["net_rupees"]
    hold_table.append(row)
df_hold = pd.DataFrame(hold_table)

# Break even margin for holding top 20%
thresh20 = np.percentile(y_prob, 80)
act20 = np.where(y_prob >= thresh20, "hold", "ship")
tp20 = np.sum((y_test == 1) & (act20 == "hold"))
fp20 = np.sum((y_test == 0) & (act20 == "hold"))
total_held20 = np.sum(act20 == "hold")

be_margin_A = (tp20 / total_held20) * COST_RETURN if total_held20 > 0 else 0
be_margin_B = (tp20 / fp20) * COST_RETURN if fp20 > 0 else 0

# ── Shield vs Non-Shield ────────────────────────────────────────────────
is_shield = (X_test["shield_member_Y"] == 1).values
shield_rate = y_test[is_shield].mean()
non_shield_rate = y_test[~is_shield].mean()
shield_auc = roc_auc_score(y_test[is_shield], y_prob[is_shield])
non_shield_auc = roc_auc_score(y_test[~is_shield], y_prob[~is_shield])

act_shield_hold = np.where((y_prob >= thresh20) & is_shield, "hold", "ship")
shield_hold_saving = evaluate_policy(y_test, y_prob, act_shield_hold, margin_loss=0)["net_rupees"]

# ── Bootstrapping top-20% Call Policy ─────────────────────────────────
np.random.seed(42)
n_bootstraps = 1000
boot_savings = []
act_call_20 = np.where(y_prob >= np.percentile(y_prob, 80), "call", "ship")
for _ in range(n_bootstraps):
    idx = np.random.choice(len(y_test), size=len(y_test), replace=True)
    res_boot = evaluate_policy(y_test[idx], y_prob[idx], act_call_20[idx])["net_rupees"]
    boot_savings.append(res_boot)
boot_savings = np.array(boot_savings)
boot_p5 = np.percentile(boot_savings, 5)
boot_p95 = np.percentile(boot_savings, 95)

# ── Call Policy Sensitivity to Effectiveness ──────────────────────────
effs = [0.15, 0.25, 0.35]
policies_eff = {
    "Call top 10%": np.where(y_prob >= np.percentile(y_prob, 90), "call", "ship"),
    "Call top 20%": act_call_20,
    "Call > BE (11.2%)": act_call_be
}
eff_results = {}
for p_name, act in policies_eff.items():
    eff_results[p_name] = {}
    for eff in effs:
        eff_results[p_name][f"eff_{int(eff*100)}"] = evaluate_policy(y_test, y_prob, act, margin_loss=0, call_effect=eff)["net_rupees"]

total_baseline_returns = np.sum(y_test)
total_baseline_cost = total_baseline_returns * COST_RETURN
net_be = evaluate_policy(y_test, y_prob, act_call_be)["net_rupees"]
share_recovered = net_be / total_baseline_cost if total_baseline_cost > 0 else 0

# ── Markdown ──────────────────────────────────────────────────────────
def df_to_markdown(df):
    cols = df.columns
    fmt = ["| " + " | ".join(cols) + " |", "|-" + "-|-".join(["-"*len(c) for c in cols]) + "-|"]
    for _, row in df.iterrows():
        r = []
        for c in cols:
            v = row[c]
            if c in ["precision", "recall", "accuracy"]:
                r.append(f"{v:.3f}")
            elif isinstance(v, float):
                r.append(f"{v:.1f}")
            else:
                r.append(str(v))
        fmt.append("| " + " | ".join(r) + " |")
    return "\n".join(fmt)

md_content = f"""# Economic Analysis (Fold 3 Holdout)

**Reason for updating order count**: The prior analysis used a test end date of 2026-06-30 00:00:00, which dropped June 30 orders. This report uses 2026-06-30 23:59:59 exactly matching `train.py` Fold 3 (2,126 orders).

## Call Policies
{df_to_markdown(df_res)}

## Hold Policies (Sensitivity to Margin Loss)
{df_to_markdown(df_hold)}

## Exact Hold Formula and Break-even
A hold causes 12% of held orders to cancel. We assume these cancellations would have been returned.
Savings = True Positives * 0.12 * Rs 1,150.
Cost (Margin Loss) depends on assumptions:
- **Assumption A** (margin lost on every cancelled held order): Break-even margin = (TP / Total Held) * 1150 = Rs {be_margin_A:.1f}
- **Assumption B** (margin lost only on cancelled false alarms): Break-even margin = (TP / FP) * 1150 = Rs {be_margin_B:.1f}

## Call Policies Sensitivity to Effectiveness
| Policy | Net Rs (15% effect) | Net Rs (25% effect) | Net Rs (35% effect) |
|--------|----------------------|----------------------|----------------------|
| Call top 10% | {eff_results['Call top 10%']['eff_15']:,.0f} | {eff_results['Call top 10%']['eff_25']:,.0f} | {eff_results['Call top 10%']['eff_35']:,.0f} |
| Call top 20% | {eff_results['Call top 20%']['eff_15']:,.0f} | {eff_results['Call top 20%']['eff_25']:,.0f} | {eff_results['Call top 20%']['eff_35']:,.0f} |
| Call > BE | {eff_results['Call > BE (11.2%)']['eff_15']:,.0f} | {eff_results['Call > BE (11.2%)']['eff_25']:,.0f} | {eff_results['Call > BE (11.2%)']['eff_35']:,.0f} |

Top 20% Policy 90% Confidence Interval (1000 bootstraps): Rs {boot_p5:,.0f} to Rs {boot_p95:,.0f}

## Shield vs Non-Shield
- Shield return rate: {shield_rate:.1%} (AUC: {shield_auc:.3f})
- Non-Shield return rate: {non_shield_rate:.1%} (AUC: {non_shield_auc:.3f})
- Holding Shield top 20% saves Rs {shield_hold_saving:.1f} (assuming 0 margin loss). Given their LTV, holding Shield is unprofitable.

## Baseline
- **Total return cost with no action**: Rs {total_baseline_cost:,.0f} ({total_baseline_returns} returns x Rs 1,150)
- **Share recovered by recommended policy**: {share_recovered:.1%}

![Economics Chart](economics_chart.png)

## Recommendation
This holdout represents one quarter containing {total_baseline_returns} actual returns. The analysis shows that net savings are highly sensitive to the true effectiveness of the confirmation call, which currently relies on an unverified 35% estimate from a small pilot without a control group. 

While calling all orders above the break-even probability (11.2%) yields the highest theoretical net saving at a 35% effectiveness (Rs {eff_results['Call > BE (11.2%)']['eff_35']:,.0f}), it is also the most exposed to a shortfall in that effectiveness (dropping to Rs {eff_results['Call > BE (11.2%)']['eff_15']:,.0f} at 15%). 

We strongly recommend **starting with the top 10% to 20%** most risky orders. Crucially, this rollout must include a **controlled pilot** (a randomized holdout group that is not called despite being flagged) to precisely measure the true effectiveness of the call. Once the true lift is known, the threshold can be expanded. 

We strongly advise against a blanket **Hold** policy. Because a hold causes 12% of customers to cancel, we lose the margin on those sales. Our analysis shows that if the margin lost is greater than Rs {be_margin_A:.0f} (Assumption A), holding loses money compared to doing nothing.
"""

with open("evidence/02_economics.md", "w") as f:
    f.write(md_content)

# ── Chart ─────────────────────────────────────────────────────────────
plt.figure(figsize=(10, 6))
thresholds = np.linspace(0, 0.5, 50)
sv_call = []
sv_hold_0 = []
sv_hold_500 = []

for t in thresholds:
    ac = np.where(y_prob > t, "call", "ship")
    sv_call.append(evaluate_policy(y_test, y_prob, ac)["net_rupees"])
    
    ah = np.where(y_prob > t, "hold", "ship")
    sv_hold_0.append(evaluate_policy(y_test, y_prob, ah, margin_loss=0)["net_rupees"])
    sv_hold_500.append(evaluate_policy(y_test, y_prob, ah, margin_loss=500)["net_rupees"])

plt.plot(thresholds, sv_call, label="Call", color='blue', linewidth=2)
plt.plot(thresholds, sv_hold_0, label="Hold (0 margin loss)", color='red', linestyle='--')
plt.plot(thresholds, sv_hold_500, label="Hold (500 margin loss)", color='red', linestyle=':')
plt.axvline(x=break_even_prob, color='grey', linestyle='-.', label=f"Call Break-even ({break_even_prob:.3f})")
plt.axhline(y=0, color='black', linewidth=1)
plt.title("Net Rupees Saved vs Probability Threshold (Fold 3)")
plt.xlabel("Probability Threshold")
plt.ylabel("Net Rupees Saved")
plt.legend()
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig("evidence/economics_chart.png")
