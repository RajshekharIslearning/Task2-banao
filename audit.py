"""
Data audit for Kestrel returns project.
Verifies hypotheses H1-H9 and surfaces additional traps.
Run: python audit.py
"""
import pandas as pd
import numpy as np
import sys

pd.set_option('display.max_columns', 50)
pd.set_option('display.width', 120)

# Force UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

# Load
train  = pd.read_csv('data/train.csv', dtype={'delivery_pincode': str})
test   = pd.read_csv('data/test_unlabelled.csv', dtype={'delivery_pincode': str})
cust   = pd.read_csv('data/customers.csv')
prod   = pd.read_csv('data/products.csv')
ss     = pd.read_csv('data/sample_submission.csv')

train['order_placed_at'] = pd.to_datetime(train['order_placed_at'])
test['order_placed_at']  = pd.to_datetime(test['order_placed_at'])

print("=" * 70)
print("H1: Row counts, duplicate order_ids, return rate")
print("=" * 70)
n_train_rows = len(train)
dup_ids = train[train.duplicated('order_id', keep=False)]
n_dup_ids = train['order_id'].duplicated().sum()
dup_sources = dup_ids['source'].value_counts()
n_unique_orders = train['order_id'].nunique()
deduped = train.drop_duplicates('order_id')
return_rate = deduped['returned'].mean()

print(f"  train rows           : {n_train_rows}")
print(f"  duplicate order_ids  : {n_dup_ids}  (extra rows beyond first occurrence)")
print(f"  source of duplicates : {dup_sources.to_dict()}")
print(f"  unique order_ids     : {n_unique_orders}")
print(f"  return rate (deduped): {return_rate:.4f}  ({return_rate*100:.2f}%)")
print()

print("=" * 70)
print("H2: Accuracy of naive 'never returned' baseline")
print("=" * 70)
naive_acc = 1 - deduped['returned'].mean()
print(f"  Naive accuracy: {naive_acc:.4f}  ({naive_acc*100:.2f}%)")
print(f"  => 95% accuracy is achievable by predicting 0 always (meaningless bar)")
print()

print("=" * 70)
print("H3: Leakage checks")
print("=" * 70)
rev = deduped[deduped['last_service_event_type'] == 'REVERSE_PICKUP']
print(f"  REVERSE_PICKUP rows in train: {len(rev)}")
if len(rev):
    print(f"    returned=1: {(rev['returned']==1).sum()}, returned=0: {(rev['returned']==0).sum()}")

for evt in ['DEMO_DONE', 'INSTALL_DONE']:
    rows = deduped[deduped['last_service_event_type'] == evt]
    print(f"  {evt} rows: {len(rows)}, returned=0: {(rows['returned']==0).sum()}, returned=1: {(rows['returned']==1).sum()}")

has_pickup = deduped['pickup_scheduled_at'].notna()
print(f"\n  pickup_scheduled_at filled: total={has_pickup.sum()}")
r1 = deduped['returned'] == 1
r0 = deduped['returned'] == 0
print(f"    among returned=1: {has_pickup[r1].mean():.4f} ({has_pickup[r1].sum()} / {r1.sum()})")
print(f"    among returned=0: {has_pickup[r0].mean():.4f} ({has_pickup[r0].sum()} / {r0.sum()})")

print(f"\n  Test last_service_event_type distribution:")
print(test['last_service_event_type'].value_counts(dropna=False).to_string())
print(f"  Test pickup_scheduled_at non-null: {test['pickup_scheduled_at'].notna().sum()}")

print(f"\n  INSTALL_BOOKED in train: {(deduped['last_service_event_type']=='INSTALL_BOOKED').sum()}")
print(f"  INSTALL_BOOKED in test:  {(test['last_service_event_type']=='INSTALL_BOOKED').sum()}")
print()

print("=" * 70)
print("H4: October 2025 order_value_inr anomaly")
print("=" * 70)
t = deduped.merge(prod[['sku','list_price_inr']], on='sku', how='left')
t['expected_value'] = t['list_price_inr'] * t['qty'] * (1 - t['discount_pct'] / 100)
t['ratio'] = t['order_value_inr'] / t['expected_value']
t['month'] = t['order_placed_at'].dt.to_period('M')
monthly_ratio = t.groupby('month')['ratio'].agg(['mean','median','count'])
print(monthly_ratio.to_string())
print()
oct25 = t[t['month'] == '2025-10']
print(f"  Oct 2025 rows: {len(oct25)}, median ratio: {oct25['ratio'].median():.2f}, mean ratio: {oct25['ratio'].mean():.2f}")
other = t[t['month'] != '2025-10']
print(f"  Other months: median ratio: {other['ratio'].median():.4f}, mean: {other['ratio'].mean():.4f}")
print()

print("=" * 70)
print("H5: Pincode 000000 as placeholder")
print("=" * 70)
pct_000000_train = (train['delivery_pincode'] == '000000').mean()
pct_000000_test  = (test['delivery_pincode'] == '000000').mean()
print(f"  Train: {pct_000000_train:.4f} ({pct_000000_train*100:.1f}%)")
print(f"  Test:  {pct_000000_test:.4f} ({pct_000000_test*100:.1f}%)")
sample_pins = train['delivery_pincode'].value_counts().head(8)
print(f"  Top pincodes:\n{sample_pins.to_string()}")
print()

print("=" * 70)
print("H6: Date ranges")
print("=" * 70)
print(f"  Train: {train['order_placed_at'].min().date()} to {train['order_placed_at'].max().date()}")
print(f"  Test:  {test['order_placed_at'].min().date()} to {test['order_placed_at'].max().date()}")
print()

print("=" * 70)
print("H7: Costs from policy and email thread")
print("=" * 70)
print("  ops-policy.txt para 4 says: Rs 1,150 per return (Finance figure)")
print("  email-thread.txt (Ritu) says: ~Rs 600")
print("  email-thread.txt (Farhan) confirms: Rs 1,150")
print("  pre-dispatch call: Rs 45, prevents ~35% of returns (policy para 7)")
print("  holds > 24h: ~12% order cancellations (policy para 7)")
print("  margin per cancelled order: NOT PROVIDED anywhere")
print()

print("=" * 70)
print("H8: Signal checks")
print("=" * 70)
d = deduped.merge(cust[['customer_id','shield_member']], on='customer_id', how='left')
d = d.merge(prod[['sku','family']], on='sku', how='left')
print("  Return rate by payment_mode:")
print(d.groupby('payment_mode')['returned'].agg(['mean','count']).sort_values('mean', ascending=False).to_string())
print("\n  Return rate by sales_channel:")
print(d.groupby('sales_channel')['returned'].agg(['mean','count']).sort_values('mean', ascending=False).to_string())
print("\n  Return rate by shield_member:")
print(d.groupby('shield_member')['returned'].agg(['mean','count']).sort_values('mean', ascending=False).to_string())
shield_pct_orders = (d['shield_member']=='Y').mean()
shield_pct_returns = d[d['returned']==1]['shield_member'].eq('Y').mean()
print(f"\n  Shield: {shield_pct_orders*100:.1f}% of orders, {shield_pct_returns*100:.1f}% of returns")
print("\n  Return rate by product family:")
print(d.groupby('family')['returned'].agg(['mean','count']).sort_values('mean', ascending=False).to_string())
print("\n  Return rate by is_gift:")
print(d.groupby('is_gift')['returned'].agg(['mean','count']).sort_values('mean', ascending=False).to_string())
print("\n  Correlation: customer_prior_returns vs returned:", round(d['customer_prior_returns'].corr(d['returned']), 4))
print("  Correlation: discount_pct vs returned:", round(d['discount_pct'].corr(d['returned']), 4))
print("  Correlation: promised_delivery_days vs returned:", round(d['promised_delivery_days'].corr(d['returned']), 4))
print()

print("=" * 70)
print("H9: Quick logistic regression time-split check")
print("=" * 70)
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler

d2 = deduped.merge(cust[['customer_id','shield_member']], on='customer_id', how='left')
d2 = d2.merge(prod[['sku','family','list_price_inr']], on='sku', how='left')
d2['shield_yn'] = (d2['shield_member']=='Y').astype(int)
d2['is_cod'] = (d2['payment_mode']=='cod').astype(int)
d2['is_marketplace'] = (d2['sales_channel']=='marketplace').astype(int)
d2['is_partner'] = (d2['sales_channel']=='partner_outlet').astype(int)
d2['is_gift_yn'] = (d2['is_gift']=='Y').astype(int)
d2['prior_return_rate'] = d2['customer_prior_returns'] / (d2['customer_prior_orders'] + 1)
d2['month'] = d2['order_placed_at'].dt.to_period('M')

# Fix Oct 2025 values (divide by 100)
d2['ov_clean'] = d2['order_value_inr'].copy()
is_oct25 = d2['month'] == '2025-10'
d2.loc[is_oct25, 'ov_clean'] = d2.loc[is_oct25, 'order_value_inr'] / 100

feats = ['is_cod','is_marketplace','is_partner','discount_pct','qty',
         'promised_delivery_days','is_gift_yn','customer_prior_orders',
         'customer_prior_returns','prior_return_rate','shield_yn','ov_clean']

d2 = d2.dropna(subset=feats + ['returned'])

cutoff = pd.Period('2026-04', 'M')
tr_mask = d2['month'] < cutoff
va_mask = d2['month'] >= cutoff

X_tr = d2[tr_mask][feats]
y_tr = d2[tr_mask]['returned']
X_va = d2[va_mask][feats]
y_va = d2[va_mask]['returned']

print(f"  Train samples: {len(X_tr)}, Val samples: {len(X_va)}")
print(f"  Val return rate: {y_va.mean():.4f}")

sc = StandardScaler()
X_tr_s = sc.fit_transform(X_tr)
X_va_s = sc.transform(X_va)

lr = LogisticRegression(max_iter=1000, random_state=42)
lr.fit(X_tr_s, y_tr)
prob_va = lr.predict_proba(X_va_s)[:,1]
auc = roc_auc_score(y_va, prob_va)
print(f"  Logistic regression AUC (time-split): {auc:.4f}")

print(f"\n  Feature coefficients (logistic, sorted by magnitude):")
for f, c in sorted(zip(feats, lr.coef_[0]), key=lambda x: abs(x[1]), reverse=True):
    print(f"    {f:30s}: {c:+.4f}")
print()

print("=" * 70)
print("ADDITIONAL TRAPS / OBSERVATIONS")
print("=" * 70)

print(f"  customers.csv rows: {len(cust)}, unique customer_ids: {cust['customer_id'].nunique()}")
print(f"  test customers matched in customers.csv: {test['customer_id'].isin(cust['customer_id']).sum()} / {len(test)}")
print(f"  train SKUs not in products.csv: {set(train['sku'].unique()) - set(prod['sku'].unique())}")
print(f"  test  SKUs not in products.csv: {set(test['sku'].unique()) - set(prod['sku'].unique())}")

print(f"\n  sample_submission rows: {len(ss)}, columns: {list(ss.columns)}")
print(f"  test_unlabelled rows:   {len(test)}")
print(f"  Row count match: {len(ss) == len(test)}")
print(f"  order_id sets match: {set(ss['order_id']) == set(test['order_id'])}")

print(f"\n  NaN counts in train key columns (non-zero only):")
key_cols = ['payment_mode','sales_channel','discount_pct','qty','order_value_inr',
            'promised_delivery_days','is_gift','customer_prior_orders','customer_prior_returns']
found_any = False
for col in key_cols:
    nans = train[col].isna().sum()
    if nans > 0:
        print(f"    {col}: {nans}")
        found_any = True
if not found_any:
    print("    (none)")

print(f"\n  Rows pre-Oct 2025 in train: {(train['order_placed_at'] < pd.Timestamp('2025-10-01')).sum()}")
print(f"  (service event timestamps for these rows may be UTC-shifted per policy para 9)")

print(f"\n  delivery_note non-null in train: {train['delivery_note'].notna().sum()} / {len(train)}")
print(f"  delivery_note non-null in test:  {test['delivery_note'].notna().sum()} / {len(test)}")

print(f"\n  Unique last_service_event_type in train (deduped):")
print(deduped['last_service_event_type'].value_counts(dropna=False).to_string())

print(f"\n  Test payment_mode distribution:")
print(test['payment_mode'].value_counts().to_string())

print(f"\n  Train month distribution (deduped):")
deduped2 = deduped.copy()
deduped2['month'] = deduped2['order_placed_at'].dt.to_period('M')
print(deduped2.groupby('month')['returned'].agg(['count','mean']).to_string())

print("\n" + "=" * 70)
print("DONE")
print("=" * 70)
