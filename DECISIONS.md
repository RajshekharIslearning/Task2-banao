# DECISIONS.md
## Kestrel Returns — Every Judgment Call

Format: question | decision | reason | who / source

This file is append-only. Add a new row each time a judgment is made during the project.
Last updated: 2026-10-09.

---

## Data preparation

| # | Question | Decision | Reason | Source |
|---|---|---|---|---|
| D-01 | How to handle 651 duplicate order_ids in train? | Keep the `crm` row; drop the `partner_feed` row. | All duplicate pairs are byte-for-byte identical in every column except `source`. The Kestrel CRM is the authoritative system (ops-policy.txt para 9). Keeping both would leak order identity across CV folds. Confirmed by running pair-wise column comparison — zero differing columns besides `source`. | Data audit (evidence/audit.py, PASS) |
| D-02 | How to fix the October 2025 order value anomaly? | Divide `order_value_inr` by 100 for all rows where `order_placed_at` is in October 2025 (2025-10-01 to 2025-10-31 inclusive). | The stored/expected ratio is exactly 100.0 for every row in that month and exactly 1.0 for every other month. Tanmay flagged the new payment gateway as the likely cause. The fix is mechanical, unambiguous, and fully reversible if the root cause changes. | Data audit §6; email-thread.txt (Tanmay) |
| D-03 | How to handle pincode '000000'? | Treat as missing (NaN). Do not use it as a location signal. | README confirms it is the system default when no address is captured (walk-in partner orders). Using it as a pincode would create a spurious "location" signal that does not exist. | README.txt; Data audit §2 |

---

## Feature selection

| # | Question | Decision | Reason | Source |
|---|---|---|---|---|
| D-04 | Use `last_service_event_type` as a feature? | **No. Excluded entirely.** | (a) Leakage: REVERSE_PICKUP appears in 100% of returned=1 rows and 0% of returned=0 rows. DEMO_DONE and INSTALL_DONE appear in 0% of returns. These values reflect the outcome, not a pre-dispatch condition. (b) Distribution shift: INSTALL_BOOKED appears in 543 test rows and zero train rows; any encoding would be unreliable on test. Both reasons are independent and either alone is sufficient to exclude the column. | Data audit §5; ops-policy.txt para 7 |
| D-05 | Use `pickup_scheduled_at` as a feature? | **No. Excluded entirely.** | Direct leakage: a reverse pickup is booked only after a return is approved (ops-policy.txt para 7). The column is filled for 94.2% of returns and 1.1% of non-returns in train; test has zero non-null values. Using it in train would inflate performance and give zero signal on test. | Data audit §5; ops-policy.txt para 7 |
| D-06 | Use `source` (crm / partner_feed) as a feature? | **No.** | After deduplication, all remaining rows have `source = crm`. The column carries no variation. | Data audit §3 |
| D-07 | Use `delivery_pincode` as a numeric or categorical feature? | **No, not directly.** Use only a binary flag: is_no_address (1 if pincode = '000000', else 0). Consider state/region lookup if time allows. | The pincode has ~8% placeholder values. Treating it as a numeric or high-cardinality categorical without handling the placeholder would introduce spurious signals. A no-address flag captures the meaningful information from the placeholder. | Data audit §2 |
| D-08 | Use `delivery_note` (free text) as a feature? | **Not in the baseline model.** May add a simple keyword flag (e.g. note_has_text: Y/N) as a low-risk proxy. | The field is 25% null in train and 26% null in test. NLP-derived features would add complexity and risk of overfitting on sparse text. The keyword flag is safe and interpretable. | Data audit §2 |

---

## Validation

| # | Question | Decision | Reason | Source |
|---|---|---|---|---|
| D-09 | How to validate the model? | Time-based split: train on orders placed before 2026-04-01 (Apr 2025 – Mar 2026, ~8,378 orders); validate on Apr 2026 – Jun 2026 (~2,126 orders). No random CV. | The test set is a future period (Jul–Sep 2026). Any random split would contaminate later orders into training, violating temporal ordering. The hold-out window covers the 3 most recent train months, matching the forward-looking nature of the test set. | Working principles; Data audit §1 |

---

## Economics and metrics

| # | Question | Decision | Reason | Source |
|---|---|---|---|---|
| D-10 | Which return cost to use? | **Rs 1,150 per return.** | This is the Finance-reported all-in figure (ops-policy.txt para 4) confirmed by Farhan Sheikh in the email thread. Ritu's Rs 600 estimate is the only contradicted claim in the thread and is not backed by any source document. | ops-policy.txt §4; email-thread.txt (Farhan) |
| D-11 | Is 95% accuracy the right target? | **No. It is not a meaningful bar.** Reporting accuracy for context only; optimising AUC, PR-AUC, and net rupee saving. | Predicting "never returned" for every order yields 88.6% accuracy without any model. A model reaching 95% accuracy needs only to correctly flag ~60% of the remaining gap. The Banao reviewers are told to judge on ranking quality and rupee value, not accuracy. | Working principles; Data audit §; SRS §2 |
| D-12 | What is the margin lost on a cancelled hold? | **Unknown. Treated as an explicit parameter, default 0.** | No document provides this number. Farhan asks for it but does not supply it. Sensitivity analysis in evidence/economics will show the break-even margin. Until the number is supplied, the default of zero is the most conservative assumption (no cost to a cancellation), which biases toward calling rather than holding — the safer action. | email-thread.txt (Farhan); SRS §3 |

---

## Action logic

| # | Question | Decision | Reason | Source |
|---|---|---|---|---|
| D-13 | When to recommend "call" vs "hold" vs "ship"? | Ship if p < call break-even (~11.2%). Call if p >= break-even and the order is not Shield. Never hold in the baseline; hold is shown as an option in the sensitivity analysis with explicit assumptions. | The call break-even is p > 45 / (0.35 × 1150) = 11.2%, approximately the base rate. Calling everyone is near break-even; the model's value is directing calls to the high-risk subset. Holding alone does not prevent a return — it only prevents it if the customer cancels (12%), which loses a sale. | SRS §3; ops-policy.txt para 7 |
| D-14 | Should Shield members ever receive a "hold" recommendation? | **Never. Maximum action for Shield members is "call".** | This is a design decision by the project author, not a Kestrel policy rule. Reason: Shield members are 22.2% of orders, 36.1% of returns, and are explicitly the highest-LTV segment (ops-policy.txt para 6). Holding their orders risks damaging the highest-value customer relationship for a saving that is near the call break-even anyway. Meenal Joshi raised this concern directly. Ritu deferred Shield to a later decision. Until that decision is made, the safe default is "call only." | Project author decision; Meenal Joshi (email-thread.txt); ops-policy.txt para 6 |

---

## Stack and reproducibility

| # | Question | Decision | Reason | Source |
|---|---|---|---|---|
| D-15 | Which ML library? | scikit-learn only (LogisticRegression + HistGradientBoostingClassifier + CalibratedClassifierCV). | Working principles specify scikit-learn. SRS §8 mentions LightGBM as an option but working principles take precedence. HistGradientBoosting is native to scikit-learn and handles mixed types without extra dependencies. | Working principles |
| D-16 | Which API framework? | FastAPI. | Named in the working principles. Faster than Flask for JSON-heavy endpoints and has automatic input validation via Pydantic. | Working principles |
| D-17 | Random seed? | 42 everywhere. | Arbitrary fixed value. Written here so it appears in exactly one place and is never a free parameter. | Working principles |
| D-18 | Which model to select? | Logistic Regression. | HistGradientBoosting scored 0.0365 AUC LOWER than Logistic Regression on the final holdout. LR is simpler, easily explainable, and less prone to edge-case extrapolation. | Model Evaluation |
