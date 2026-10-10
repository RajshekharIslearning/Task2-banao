# Kestrel Returns — Data Audit
## `evidence/01_data_audit.md`

> Source: `python evidence/audit.py` run 2026-10-09. Full console output: [evidence/audit_output.txt](audit_output.txt). Exit code: **0**. Checks: **15 passed, 0 failed**.

---

## 1. Shapes and date ranges

| File | Rows | Unique IDs | Notes |
|---|---|---|---|
| train.csv (raw) | 11,155 | 10,504 order_ids | 651 extra rows from partner-feed re-import |
| train.csv (deduped) | 10,504 | 10,504 | Used for all analysis below |
| test_unlabelled.csv | 2,096 | 2,096 | Matches sample_submission.csv exactly |
| customers.csv | 9,000 | 9,000 | No duplicates; all train+test customer_ids present |
| products.csv | 21 | 21 | All train+test SKUs present |
| sample_submission.csv | 2,096 | 2,096 | Columns: order_id, score |

| Dataset | Start | End |
|---|---|---|
| Train | 2025-04-01 | 2026-06-30 |
| Test | 2026-07-01 | 2026-09-30 |

Test is a strictly future period relative to train. Time-based validation is required.

---

## 2. Missing values

No NaN values in any key feature column (payment_mode, sales_channel, discount_pct, qty, order_value_inr, promised_delivery_days, is_gift, customer_prior_orders, customer_prior_returns, delivery_pincode, sku, customer_id).

| Column | Condition | Count | Action |
|---|---|---|---|
| delivery_pincode | value = '000000' | train 889 (8.0%), test 176 (8.4%) | Treat as missing; README confirms placeholder for walk-in orders |
| delivery_note | null | train 2,752/11,155 (25%), test 538/2,096 (26%) | Sparse free text; handle missingness before any text feature |

---

## 3. Duplicate proof

| Item | Value |
|---|---|
| Duplicate order_id extra rows | 651 |
| Source in duplicate rows | partner_feed: 651, crm: 651 — exactly one of each per pair |
| Columns where pairs differ (besides `source`) | **NONE** |

**Confirmed:** every duplicate pair is byte-for-byte identical in all columns except `source`. The partner-feed row adds no new information.

**Decision:** keep the `crm` row, drop `partner_feed`. Reason: ops-policy.txt para 9 identifies the Kestrel CRM as the authoritative system from Oct 2025; the CRM row is present for all periods including legacy records migrated from Zoho.

---

## 4. Join coverage

| Join | Coverage |
|---|---|
| train → products.csv on sku | 100% (0 unmatched SKUs) |
| test → products.csv on sku | 100% |
| train → customers.csv on customer_id | 100% |
| test → customers.csv on customer_id | 100% |

No cold-start problem for Shield status or product family on either set.

---

## 5. Return rate by month

*(Deduped train, n=10,504, overall rate 11.4%)*

| Month | Orders | Returns | Rate (%) |
|---|---|---|---|
| 2025-04 | 661 | 99 | 15.0 |
| 2025-05 | 674 | 81 | 12.0 |
| 2025-06 | 678 | 64 | 9.4 |
| 2025-07 | 736 | 87 | 11.8 |
| 2025-08 | 714 | 92 | 12.9 |
| 2025-09 | 707 | 60 | 8.5 |
| 2025-10 | 700 | 81 | 11.6 |
| 2025-11 | 698 | 74 | 10.6 |
| 2025-12 | 684 | 70 | 10.2 |
| 2026-01 | 719 | 81 | 11.3 |
| 2026-02 | 664 | 85 | 12.8 |
| 2026-03 | 743 | 81 | 10.9 |
| 2026-04 | 705 | 85 | 12.1 |
| 2026-05 | 722 | 83 | 11.5 |
| 2026-06 | 699 | 77 | 11.0 |

Rate is stable across months (range 8.5–15.0%). No structural trend; the validation window (Apr–Jun 2026) is representative of the overall rate.

---

## 6. Return rate by payment mode

| Payment mode | Return rate | Count |
|---|---|---|
| **cod** | **18.8%** | 3,152 |
| emi | 9.1% | 1,278 |
| prepaid_card | 8.8% | 2,153 |
| prepaid_upi | 7.7% | 3,921 |

COD returns at 2.4× the prepaid-UPI rate. Strongest single categorical signal.

---

## 7. Return rate by channel

| Channel | Return rate | Count |
|---|---|---|
| marketplace | 13.6% | 2,869 |
| web | 11.2% | 2,766 |
| app | 10.7% | 3,582 |
| partner_outlet | 9.1% | 1,287 |

Marketplace is elevated; partner outlet is lowest (face-to-face purchase may reduce impulse returns).

---

## 8. Return rate by product family

| Family | Return rate | Count |
|---|---|---|
| Robot Vacuum | 19.5% | 1,554 |
| Water Purifier | 14.8% | 1,451 |
| Air Fryer | 12.0% | 1,516 |
| Room Heater | 11.7% | 1,525 |
| Induction Cooktop | 8.3% | 1,476 |
| Mixer Grinder | 6.8% | 1,451 |
| Ceiling Fan | 6.7% | 1,531 |

Robot Vacuum returns at nearly 3× the rate of Ceiling Fan. High-complexity, high-price items lead.

---

## 9. Return rate by Shield membership

| Shield member | Return rate | Count |
|---|---|---|
| Y | 18.6% | 2,327 |
| N | 9.4% | 8,177 |

Shield members are **22.2% of orders** and **36.1% of returns** — over-represented in returns but not a majority. Meenal's claim that "most returns are Shield customers" is not supported by the data; the correct statement is that Shield members return at roughly twice the rate of non-Shield members.

Hypothesis (not confirmed): free 30-day returns under the Shield plan may reduce the cost barrier to returning, leading to higher return rates among this segment. This is structurally plausible but not directly measurable from this data.

---

## 10. Return rate by gift order

| is_gift | Return rate | Count |
|---|---|---|
| Y | 16.5% | 726 |
| N | 11.0% | 9,778 |

Gift orders return at 1.5× the base rate (recipient mismatch, unwanted items).

---

## 11. Return rate by discount band

| Discount (%) | Return rate | Count |
|---|---|---|
| 0 | 11.3% | 53 |
| 1–5 | 9.0% | 3,073 |
| 6–10 | 11.3% | 3,399 |
| 11–15 | 11.5% | 2,014 |
| **15+** | **15.4%** | 1,965 |

Weak monotonic signal; high-discount orders (15%+) return measurably more. Small discounts (1–5%) are the safest band.

---

## 12. Return rate by promised delivery days band

| Promised days | Return rate | Count |
|---|---|---|
| 1–3 | 7.6% | 2,300 |
| 4–5 | 9.6% | 4,207 |
| 6–7 | 14.4% | 2,900 |
| **8+** | **18.7%** | 1,097 |

Strong monotonic signal: longer promised lead times correlate with higher returns (expectation management issue, or slower logistics regions).

---

## 13. Return rate by prior returns band

| Prior returns | Return rate | Count |
|---|---|---|
| 0 | 9.1% | 9,119 |
| 1 | 19.9% | 1,038 |
| 2 | 40.8% | 223 |
| **3+** | **61.3%** | 124 |

Strongest monotonic signal in the dataset. A customer with 3+ prior returns converts at 6.7× the base rate. Prior return count is the highest-magnitude numeric predictor.

---

## 14. Leakage proof

### Return rate by `last_service_event_type` (train, deduped)

| Event type | Count | Return rate (%) |
|---|---|---|
| REVERSE_PICKUP | 750 | **100.0** |
| TECH_VISIT | 447 | 38.5 |
| NONE | 6,536 | 4.3 |
| DEMO_DONE | 1,417 | **0.0** |
| INSTALL_DONE | 1,354 | **0.0** |

REVERSE_PICKUP is a perfect predictor of returns (100%). DEMO_DONE and INSTALL_DONE are perfect predictors of non-returns (0%). These are outcomes recorded *after* dispatch; using them in a pre-dispatch model is data leakage.

> **Why they are leaky:** ops-policy.txt para 7 states that a reverse pickup is booked *after a return is approved*. Tanmay confirms service and pickup columns are pulled from the service system as of export day, not at dispatch time.

### `pickup_scheduled_at` fill rate by outcome

| returned | Fill rate |
|---|---|
| 0 | 1.1% |
| 1 | 94.2% |

Pickup is scheduled only after return approval. In test: **0 rows** have pickup_scheduled_at filled.

### Event-type distribution: train vs test

| Set | Event types |
|---|---|
| Train only | REVERSE_PICKUP, DEMO_DONE, INSTALL_DONE, TECH_VISIT |
| **Test only** | **INSTALL_BOOKED** (543 rows) |
| Both | NONE |

A model trained on `last_service_event_type` would see a category in test it has never seen in train, even if leaky values were removed. This column must not be used as a feature in any form.

---

## 15. October 2025 order value ratio by month

*(Ratio = stored order_value_inr / list_price × qty × (1 − discount/100))*

| Month | Median ratio | Mean ratio | Count |
|---|---|---|---|
| All other months | 1.00 | 1.00 | — |
| **2025-10** | **100.00** | **100.00** | 700 |

Every October 2025 order value is exactly 100× the expected value. Every other month matches exactly. Consistent with Tanmay's note about the new payment gateway.

**Fix:** divide `order_value_inr` by 100 for rows where month = October 2025 before use in any feature.

---

## 16. Timezone note vs columns used

- **Affected by UTC bug:** `last_service_event_type` event timestamps and `pickup_scheduled_at` (Zoho-era resolution events, pre-Oct 2025 rows = 4,418 in train).
- **Not affected:** `order_placed_at` is an order placement timestamp, not a service event; it should be in IST across all rows.
- **Impact on model:** zero. Both leaky columns are excluded entirely. `order_placed_at` is used only for the time-based train/validation split, not as a model feature.

---

## 17. Email thread claims: supported or contradicted

| Claim | Verdict | Evidence |
|---|---|---|
| Ritu: each return costs ~Rs 600 | **CONTRADICTED** | ops-policy.txt para 4 states Rs 1,150. Farhan confirms. |
| Ritu: 95%+ accuracy target | **CONTRADICTED (misleading bar)** | Predicting "never return" gives 88.6%. 95% requires no skill. |
| Tanmay: partner-outlet orders appear twice | **SUPPORTED** | 651 extra rows; each pair = one crm + one partner_feed row, identical except source. |
| Tanmay: October values unchecked (new gateway) | **SUPPORTED** | Oct 2025 ratio = 100.0 exactly; all other months = 1.0 exactly. |
| Tanmay: walk-in orders get default pincode | **SUPPORTED** | 8.0% of train rows have '000000'; README confirms placeholder. |
| Tanmay: service/pickup pulled at export day | **SUPPORTED — and this is why they are leaky** | REVERSE_PICKUP → 100% returned. Pickup fill 94% in returns vs 1.1% in non-returns. |
| Farhan: return cost Rs 1,150, not 600 | **SUPPORTED** | ops-policy.txt para 4 matches exactly. |
| Farhan: held orders lead to cancellations | **SUPPORTED** | ops-policy.txt para 7: >24h hold → ~12% cancellations. |
| Meenal: "most returns are Shield customers" | **PARTIALLY SUPPORTED — over-represented, not a majority** | Shield = 36.1% of returns; 36% is a large minority, not a majority. Meenal overstates it. |
| Meenal: confirmation calls seemed to work | **SUPPORTED** | ops-policy.txt para 7: pilot prevented ~35% of returns on called orders. |
| Meenal: Shield customers are highest-LTV | **SUPPORTED** | ops-policy.txt para 6 states explicitly "highest lifetime value of any segment." |

---

## 18. What this means for the model

1. Exclude `last_service_event_type` and `pickup_scheduled_at` entirely — they carry the outcome, not pre-dispatch information.
2. Deduplicate on `order_id` keeping the `crm` row before any training or cross-validation — otherwise folds see the same order twice.
3. Divide October 2025 `order_value_inr` by 100 before use — every other month is correct as stored.
4. Treat pincode `000000` as missing — do not use it as a real location signal.
5. Validate on Apr–Jun 2026 (held-out, time-ordered) — never use random splits on this dataset.
6. COD (18.8% rate) vs prepaid-UPI (7.7%) is the strongest single binary signal; prior returns is the strongest numeric signal (corr = 0.24 with returned; rate climbs from 9% at 0 prior returns to 61% at 3+).
7. Shield members return at 18.6% vs 9.4% for non-Shield — the model must score them honestly, but the action logic must never auto-hold them (see DECISIONS.md).
8. `INSTALL_BOOKED` appears in 543 test rows and zero train rows — do not use `last_service_event_type` as a feature even after removing leaky values, because its distribution shifts between train and test.
