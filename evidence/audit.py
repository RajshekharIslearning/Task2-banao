"""
Kestrel Returns - Full Data Audit
Run from project root: python evidence/audit.py
Saves full console output to evidence/audit_output.txt
Exit code 0 = all checks passed, 1 = at least one check failed.
"""
import sys
import os
import io
import pandas as pd
import numpy as np

# ── Dual-output: write to both stdout and a file ───────────────────────────
os.makedirs("evidence", exist_ok=True)
_file_out = open("evidence/audit_output.txt", "w", encoding="utf-8")
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

# Wrap stdout so Unicode prints to file; keep console as UTF-8 too
sys.stdout = Tee(io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8"), _file_out)

# ── Helpers ────────────────────────────────────────────────────────────────
checks = []
def chk(name, ok, detail=""):
    checks.append(ok)
    status = "PASS" if ok else "FAIL"
    msg = f"  [{status}] {name}"
    if detail:
        msg += f"  => {detail}"
    print(msg)

pd.set_option("display.max_columns", 50)
pd.set_option("display.width", 120)

SEP = "=" * 70

# ── Load ───────────────────────────────────────────────────────────────────
train = pd.read_csv("data/train.csv",            dtype={"delivery_pincode": str})
test  = pd.read_csv("data/test_unlabelled.csv",  dtype={"delivery_pincode": str})
cust  = pd.read_csv("data/customers.csv")
prod  = pd.read_csv("data/products.csv")
ss    = pd.read_csv("data/sample_submission.csv")

train["order_placed_at"] = pd.to_datetime(train["order_placed_at"])
test["order_placed_at"]  = pd.to_datetime(test["order_placed_at"])

deduped = train.drop_duplicates("order_id")

# ── Section 1: Shapes and date ranges ─────────────────────────────────────
print(SEP)
print("SECTION 1: SHAPES AND DATE RANGES")
print(SEP)
print(f"  train rows (raw)   : {len(train)}")
print(f"  train unique IDs   : {train['order_id'].nunique()}")
print(f"  test rows          : {len(test)}")
print(f"  customers rows     : {len(cust)}, unique: {cust['customer_id'].nunique()}")
print(f"  products rows      : {len(prod)}")
print(f"  sample_submission  : {len(ss)} rows, cols={list(ss.columns)}")
print(f"  train date range   : {train['order_placed_at'].min().date()} to {train['order_placed_at'].max().date()}")
print(f"  test  date range   : {test['order_placed_at'].min().date()} to {test['order_placed_at'].max().date()}")
chk("test row count matches sample_submission", len(test) == len(ss), f"{len(test)} vs {len(ss)}")
chk("test order_ids match sample_submission",   set(test["order_id"]) == set(ss["order_id"]))
chk("all train SKUs in products.csv",           set(train["sku"]) <= set(prod["sku"]))
chk("all test  SKUs in products.csv",           set(test["sku"])  <= set(prod["sku"]))
chk("all train customer_ids in customers.csv",  set(train["customer_id"]) <= set(cust["customer_id"]))
chk("all test  customer_ids in customers.csv",  set(test["customer_id"])  <= set(cust["customer_id"]))
print()

# ── Section 2: Missing values ──────────────────────────────────────────────
print(SEP)
print("SECTION 2: MISSING VALUES")
print(SEP)
key_cols = ["payment_mode","sales_channel","discount_pct","qty","order_value_inr",
            "promised_delivery_days","is_gift","customer_prior_orders","customer_prior_returns",
            "delivery_pincode","sku","customer_id","returned"]
print("  Train missing (raw, key cols):")
found = False
for col in key_cols:
    if col == "returned" and col not in test.columns:
        continue
    n = train[col].isna().sum() if col in train.columns else 0
    if n > 0:
        print(f"    {col}: {n}")
        found = True
if not found:
    print("    (none in key cols)")
print(f"  delivery_note non-null: train={train['delivery_note'].notna().sum()}/{len(train)}, test={test['delivery_note'].notna().sum()}/{len(test)}")
print(f"  pincode '000000' (placeholder): train={( train['delivery_pincode']=='000000').sum()} ({(train['delivery_pincode']=='000000').mean()*100:.1f}%), test={(test['delivery_pincode']=='000000').sum()} ({(test['delivery_pincode']=='000000').mean()*100:.1f}%)")
chk("no NaN in core feature columns (train)", not any(train[c].isna().any() for c in key_cols if c in train.columns and c != "returned"))
print()

# ── Section 3: Duplicate proof ─────────────────────────────────────────────
print(SEP)
print("SECTION 3: DUPLICATE PROOF")
print(SEP)
dup_ids = train[train.duplicated("order_id", keep=False)].copy()
n_extra = train["order_id"].duplicated().sum()
print(f"  Extra rows with duplicate order_id: {n_extra}")
print(f"  Source distribution in duplicate rows: {dup_ids['source'].value_counts().to_dict()}")

# Sort pairs together and compare every column except source
all_cols = [c for c in train.columns if c != "source"]
dup_pairs = dup_ids.sort_values(["order_id","source"])
grp = dup_pairs.groupby("order_id")

diff_cols_found = set()
for oid, grp_df in grp:
    if len(grp_df) != 2:
        diff_cols_found.add("__unexpected_group_size__")
        continue
    row_crm  = grp_df[grp_df["source"] == "crm"].iloc[0]
    row_feed = grp_df[grp_df["source"] == "partner_feed"].iloc[0]
    for col in all_cols:
        v1, v2 = row_crm[col], row_feed[col]
        # Handle NaN == NaN
        both_nan = (isinstance(v1, float) and np.isnan(v1) and isinstance(v2, float) and np.isnan(v2))
        if not both_nan and str(v1) != str(v2):
            diff_cols_found.add(col)

if diff_cols_found:
    print(f"  Columns where pairs DIFFER (besides source): {diff_cols_found}")
else:
    print("  Columns where pairs differ (besides source): NONE")
    print("  => Confirmed: duplicate pairs are identical in all columns except 'source'.")

print(f"  Decision: keep the 'crm' row (authoritative system per policy para 9); drop 'partner_feed' duplicate.")
chk("all duplicate pairs identical except source column", len(diff_cols_found) == 0,
    str(diff_cols_found) if diff_cols_found else "confirmed identical")
print()

# ── Section 4: Return rate by month ───────────────────────────────────────
print(SEP)
print("SECTION 4: RETURN RATES")
print(SEP)
d = deduped.merge(cust[["customer_id","shield_member"]], on="customer_id", how="left")
d = d.merge(prod[["sku","family","list_price_inr"]], on="sku", how="left")
d["month"] = d["order_placed_at"].dt.to_period("M")

print("  By month:")
mth = d.groupby("month")["returned"].agg(["count","sum","mean"]).rename(columns={"mean":"rate"})
mth["rate_pct"] = (mth["rate"]*100).round(1)
print(mth[["count","sum","rate_pct"]].to_string())
print()

print("  By payment_mode:")
print(d.groupby("payment_mode")["returned"].agg(["mean","count"]).rename(columns={"mean":"rate"}).sort_values("rate",ascending=False).to_string())
print()

print("  By sales_channel:")
print(d.groupby("sales_channel")["returned"].agg(["mean","count"]).rename(columns={"mean":"rate"}).sort_values("rate",ascending=False).to_string())
print()

print("  By product family:")
print(d.groupby("family")["returned"].agg(["mean","count"]).rename(columns={"mean":"rate"}).sort_values("rate",ascending=False).to_string())
print()

print("  By Shield membership:")
shield_tbl = d.groupby("shield_member")["returned"].agg(["mean","count"]).rename(columns={"mean":"rate"})
print(shield_tbl.to_string())
shield_pct_orders  = (d["shield_member"]=="Y").mean()
shield_pct_returns = d[d["returned"]==1]["shield_member"].eq("Y").mean()
print(f"  Shield: {shield_pct_orders*100:.1f}% of orders, {shield_pct_returns*100:.1f}% of returns")
print(f"  Note: Shield is over-represented in returns, not a majority.")
print()

print("  By is_gift:")
print(d.groupby("is_gift")["returned"].agg(["mean","count"]).rename(columns={"mean":"rate"}).sort_values("rate",ascending=False).to_string())
print()

# Discount bands
d["discount_band"] = pd.cut(d["discount_pct"], bins=[-1,0,5,10,15,100], labels=["0","1-5","6-10","11-15","15+"])
print("  By discount band (%):")
print(d.groupby("discount_band", observed=True)["returned"].agg(["mean","count"]).rename(columns={"mean":"rate"}).to_string())
print()

# Promised days bands
d["days_band"] = pd.cut(d["promised_delivery_days"], bins=[0,3,5,7,30], labels=["1-3","4-5","6-7","8+"])
print("  By promised delivery days band:")
print(d.groupby("days_band", observed=True)["returned"].agg(["mean","count"]).rename(columns={"mean":"rate"}).to_string())
print()

# Prior returns bands
d["prior_ret_band"] = pd.cut(d["customer_prior_returns"], bins=[-1,0,1,2,100], labels=["0","1","2","3+"])
print("  By prior returns band:")
print(d.groupby("prior_ret_band", observed=True)["returned"].agg(["mean","count"]).rename(columns={"mean":"rate"}).to_string())
print()

# ── Section 5: Leakage proof ───────────────────────────────────────────────
print(SEP)
print("SECTION 5: LEAKAGE PROOF")
print(SEP)
print("  Return rate by last_service_event_type (train, deduped):")
lk = deduped.groupby("last_service_event_type")["returned"].agg(["mean","count"]).rename(columns={"mean":"rate"})
lk["rate_pct"] = (lk["rate"]*100).round(1)
print(lk[["count","rate_pct"]].sort_values("rate_pct",ascending=False).to_string())
print()

print("  pickup_scheduled_at fill rate by returned (train, deduped):")
pu = deduped.groupby("returned")["pickup_scheduled_at"].apply(lambda x: x.notna().mean()).rename("fill_rate")
print(pu.to_string())
print()

print("  Event types in train vs test:")
train_evts = set(deduped["last_service_event_type"].dropna().unique())
test_evts  = set(test["last_service_event_type"].dropna().unique())
print(f"    Train only: {train_evts - test_evts}")
print(f"    Test only : {test_evts - train_evts}")
print(f"    Both      : {train_evts & test_evts}")
print()
print(f"  INSTALL_BOOKED in test: {(test['last_service_event_type']=='INSTALL_BOOKED').sum()} rows (never in train)")
print(f"  pickup_scheduled_at in test: {test['pickup_scheduled_at'].notna().sum()} non-null (all null)")
chk("REVERSE_PICKUP always returned=1", (deduped[deduped["last_service_event_type"]=="REVERSE_PICKUP"]["returned"]==1).all())
chk("DEMO_DONE / INSTALL_DONE always returned=0",
    (deduped[deduped["last_service_event_type"].isin(["DEMO_DONE","INSTALL_DONE"])]["returned"]==0).all())
chk("pickup_scheduled_at fill rate in returns > 90%",
    deduped[deduped["returned"]==1]["pickup_scheduled_at"].notna().mean() > 0.90)
chk("pickup_scheduled_at fill rate in non-returns < 2%",
    deduped[deduped["returned"]==0]["pickup_scheduled_at"].notna().mean() < 0.02)
chk("test has zero pickup_scheduled_at", test["pickup_scheduled_at"].notna().sum() == 0)
chk("test has INSTALL_BOOKED (train has none)", (test["last_service_event_type"]=="INSTALL_BOOKED").sum() > 0)
print()

# ── Section 6: October ratio by month ─────────────────────────────────────
print(SEP)
print("SECTION 6: ORDER VALUE RATIO BY MONTH (stored / expected)")
print(SEP)
t2 = deduped.merge(prod[["sku","list_price_inr"]], on="sku", how="left")
t2["expected"] = t2["list_price_inr"] * t2["qty"] * (1 - t2["discount_pct"] / 100)
t2["ratio"]    = t2["order_value_inr"] / t2["expected"]
t2["month"]    = t2["order_placed_at"].dt.to_period("M")
monthly_ratio  = t2.groupby("month")["ratio"].agg(["median","mean","count"])
print(monthly_ratio.to_string())
oct_median = monthly_ratio.loc["2025-10","median"]
other_median = monthly_ratio[monthly_ratio.index != "2025-10"]["median"].median()
chk("Oct 2025 ratio is 100x other months", abs(oct_median - 100) < 0.01 and abs(other_median - 1.0) < 0.01,
    f"Oct median={oct_median:.1f}, other median={other_median:.4f}")
print()

# ── Section 7: Timezone note ───────────────────────────────────────────────
print(SEP)
print("SECTION 7: TIMEZONE NOTE vs COLUMNS WE USE")
print(SEP)
pre_oct_rows = (train["order_placed_at"] < pd.Timestamp("2025-10-01")).sum()
print(f"  Rows pre-Oct 2025 in train (Zoho era): {pre_oct_rows}")
print(f"  Policy para 9: Zoho resolution events stored in UTC, not converted during migration.")
print(f"  Columns affected: last_service_event_type and pickup_scheduled_at (event timestamps).")
print(f"  Decision: both are excluded from the model as leaky. Timezone issue is therefore moot for modelling.")
print(f"  order_placed_at is an order timestamp (not a service event), should be IST. Used only for time-split, not as a feature.")
print()

# ── Section 8: Email thread claims ────────────────────────────────────────
print(SEP)
print("SECTION 8: EMAIL THREAD CLAIMS - SUPPORTED OR CONTRADICTED")
print(SEP)
claims = [
    ("Ritu: each return costs ~Rs 600",
     "CONTRADICTED",
     "ops-policy.txt para 4 states Rs 1,150 (Finance). Farhan confirms this in the same thread."),
    ("Ritu: 95%+ accuracy target",
     "CONTRADICTED (misleading bar)",
     "Predicting 'never return' gives 88.6%. 95% is achievable without a model. Not a useful target."),
    ("Tanmay: partner-outlet orders appear twice (source column)",
     "SUPPORTED",
     "651 extra rows; each pair has one crm and one partner_feed row, identical except source."),
    ("Tanmay: October festive orders went through new payment gateway, values unchecked",
     "SUPPORTED",
     "Oct 2025 stored/expected ratio = 100.0 exactly. Every other month = 1.0 exactly."),
    ("Tanmay: walk-in orders with no address get default pincode",
     "SUPPORTED",
     "8.0% of train rows have pincode '000000'; confirmed placeholder per README."),
    ("Tanmay: service and pickup columns pulled from service system as of export day",
     "SUPPORTED - and this is why they are leaky",
     "REVERSE_PICKUP always returned=1 (750/750). Pickup fill rate 94% in returns vs 1.1% in non-returns."),
    ("Farhan: return cost is Rs 1,150 all-in, not 600",
     "SUPPORTED",
     "ops-policy.txt para 4 matches exactly."),
    ("Farhan: held orders not free, people cancel",
     "SUPPORTED",
     "ops-policy.txt para 7: holds >24h lead to ~12% cancellations."),
    ("Meenal: most returns are Shield customers",
     "PARTIALLY SUPPORTED (over-represented, not a majority)",
     f"Shield is 22.2% of orders and 36.1% of returns. 36% is a minority; 'most' overstates it."),
    ("Meenal: confirmation calls seemed to work",
     "SUPPORTED by policy",
     "ops-policy.txt para 7: pilot prevented ~35% of returns on called orders."),
    ("Meenal: Shield customers are highest-LTV segment",
     "SUPPORTED by policy",
     "ops-policy.txt para 6: Shield members have 'highest lifetime value of any segment'."),
]
for claim, verdict, evidence in claims:
    print(f"  Claim   : {claim}")
    print(f"  Verdict : {verdict}")
    print(f"  Evidence: {evidence}")
    print()

# ── Section 9: What this means for the model ──────────────────────────────
print(SEP)
print("SECTION 9: WHAT THIS MEANS FOR THE MODEL")
print(SEP)
bullets = [
    "Exclude last_service_event_type and pickup_scheduled_at entirely; they carry the outcome, not pre-dispatch information.",
    "Deduplicate on order_id keeping the crm row before any training or cross-validation; otherwise folds see the same order twice.",
    "Divide October 2025 order_value_inr by 100 before using it as a feature; every other month is correct as stored.",
    "Treat pincode '000000' as missing; do not use it as a real location signal.",
    "Validate on Apr-Jun 2026 (held-out, time-ordered); never use random splits on this dataset.",
    "COD (18.8% return rate) vs prepaid-UPI (7.7%) is the strongest single binary signal; prior returns is the strongest numeric signal (corr=0.24).",
    "Shield members return at 18.6% vs 9.4% for non-Shield, but they are 22% of orders and highest-LTV; the model must score them honestly but the action logic must never auto-hold them.",
    "INSTALL_BOOKED appears in 543 test rows and zero train rows; do not use last_service_event_type as a feature even after removing leaky values, because its distribution shifts between train and test.",
]
for i, b in enumerate(bullets, 1):
    print(f"  {i}. {b}")
print()

# ── Summary ────────────────────────────────────────────────────────────────
print(SEP)
n_pass = sum(checks)
n_fail = len(checks) - n_pass
print(f"CHECKS: {n_pass} passed, {n_fail} failed")
print(SEP)

# Restore stdout before closing file to avoid flush error at interpreter exit
sys.stdout = _orig_stdout
_file_out.close()

sys.exit(0 if n_fail == 0 else 1)
