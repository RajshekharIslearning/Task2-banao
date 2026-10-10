# Software Requirements Specification
## Kestrel Home — Pre-Dispatch Returns Risk Service (Variant A)

Version 1.0 · Author: Rajshekhar · Status: Draft for build

---

## 1. Introduction

### 1.1 Purpose
Defines what must be built and delivered for Banao Task 2: a model, a service (endpoint + screen), evidence, a memo to Ritu, a screen recording, and the submission form.

### 1.2 Scope
A system that scores a single order **at dispatch time** for return risk and explains the score to Kestrel staff in plain language. It also recommends an action (ship / call / hold) using Kestrel's own cost numbers, not raw accuracy.

### 1.3 Stakeholders
| Person | Role | What they care about |
|---|---|---|
| Ritu Deshpande | Head of D2C Ops (client) | Fewer returns; promised 95% accuracy to the board; wants "flag and hold" |
| Farhan Sheikh | Finance Controller | Rs 1,150 per return (not 600); cost of holds; no per-order model bill without a stated number |
| Meenal Joshi | Service Desk Manager | Don't hold Shield customers' orders; confirmation calls looked promising |
| Tanmay Kulkarni | Data & IT | Data export caveats |
| Banao reviewers | Evaluators | Honesty, judgment, working software, reproducibility |

### 1.4 Definitions
- **Dispatch time**: the moment the warehouse sees the order. Only information available then may be used.
- **Leakage**: using information that only exists because the outcome already happened.
- **Shield**: Kestrel's paid plan (free 30-day returns, free service, 24-month cover).

---

## 2. Data facts that shape the requirements (verified from the pack)

| Fact | Evidence | Consequence |
|---|---|---|
| Base return rate is ~11.4% | train: 11,155 orders | Predicting "no return" for everyone scores ~88.6% accuracy. **95% accuracy is not a meaningful bar**; it must be reframed. |
| `last_service_event_type = REVERSE_PICKUP` ⇒ returned = 1 in 100% of 789 rows | train | Direct leakage. Policy §7: pickup is booked *after* a return is approved. |
| `pickup_scheduled_at` present for 94% of returns vs 1.1% of non-returns | train | Leakage. Test has **0** pickup values. |
| `DEMO_DONE` / `INSTALL_DONE` ⇒ returned = 0 in 100% of 2,944 rows | train | Post-delivery states; also leakage. Test contains none. |
| Test has `INSTALL_BOOKED` (543 rows); train has none | test vs train | Distribution shift. A model trained on service columns would be wrong on test. |
| 651 duplicate `order_id`s in train, all `source = partner_feed` | train | Must deduplicate before training/CV, or folds leak. |
| `order_value_inr` max is 5.88M in train vs 57K in test; Tanmay flagged the October gateway | train describe | Corrupt values (likely unit/scale error). Detect and repair or cap; do not trust blindly. |
| Pincode `000000` on ~8% of train | train | A placeholder, not a location. Treat as "missing". |
| Timestamps: Zoho-era resolution events are in UTC, rest in IST (policy §9) | policy | Any time-based feature must be normalised; avoid features depending on those events. |
| Train: Apr 2025–Jun 2026; test: Jul–Sep 2026 | dates | Test is a **future** period. Validation must be time-based, not random. |
| COD return rate 18.8% vs 7.6–9.0% for prepaid/EMI | train | Strong legitimate signal. |

---

## 3. Economic model (Kestrel's own numbers)

- Cost per return: **Rs 1,150** (Finance, policy §4) — not Rs 600.
- Pre-dispatch confirmation call: **Rs 45**, prevents ~**35%** of returns on called orders (pilot, §7).
- Hold >24h: ~**12%** of held orders are cancelled by the customer (§7). Margin lost per cancelled order is **not given** → must be an explicit, adjustable assumption.

**Call break-even:** call if `p × 0.35 × 1150 > 45` → `p > ~11.2%`. This is roughly the base rate, so calling everyone is near break-even; a model's value is in calling the high-risk subset and *not* calling the rest.

**Hold:** holding alone does not prevent a return; it only avoids one when the customer cancels (12%), and that loses a sale. Holding is therefore likely worse than calling. The system must compute this rather than assume it.

---

## 4. Functional requirements

### 4.1 Model and predictions
| ID | Requirement |
|---|---|
| FR-1 | Train only on features available at dispatch. Exclude `last_service_event_type`, `pickup_scheduled_at`, and `returned` itself from the feature set. Document each exclusion. |
| FR-2 | Deduplicate partner-feed repeats before training and validation (keep one row per `order_id`). |
| FR-3 | Handle bad `order_value_inr` (gateway issue) with a documented rule; derive a cleaner value (e.g. from list price × qty × discount) where possible. |
| FR-4 | Treat pincode `000000` as missing. Join `customers.csv` and `products.csv`. Candidate features: payment mode, channel, discount, qty, promised days, gift, prior orders/returns, prior return rate, Shield, family, price, tenure, note flags. |
| FR-5 | Validate with a time-based split (train on earlier months, validate on the latest ~3 months) to mimic the test period. |
| FR-6 | Output a score per order where higher = more likely returned. Probabilities should be calibrated; report calibration. |
| FR-7 | Produce `predictions.csv`: one row per `order_id` in `test_unlabelled.csv`, columns exactly `order_id, score`, no missing or duplicate IDs, same row count as test (2,096). |
| FR-8 | Before submitting, write the expected score and reasoning in the form (see §7). The metric is not stated; assume ranking-based (e.g. AUC / PR-AUC) because a score is requested, and say so. |

### 4.2 Service (API)
| ID | Requirement |
|---|---|
| FR-9 | `POST /predict` accepts one order as JSON using the raw column names (excluding leaky fields; if sent, they are ignored and a warning is returned). |
| FR-10 | Returns JSON: `score`, `risk_band`, `recommended_action` (ship / call / hold), `expected_saving_inr`, and `reasons` (top factors in plain English, e.g. "Cash on delivery orders return about twice as often"). |
| FR-11 | Validates input; returns clear 4xx errors for missing or invalid fields. Never crashes on unknown SKU or customer (fallback with a flag). |
| FR-12 | `GET /health` returns status and model version. |
| FR-13 | Reasons are generated **locally** (e.g. SHAP or coefficient-based templates). No paid API required. |
| FR-14 | If an LLM is used for wording, it is optional; with no key the service still starts and falls back to templated reasons with a polite notice. |

### 4.3 Screen
| ID | Requirement |
|---|---|
| FR-15 | One page with a form (or sample-order picker) that calls `/predict` and shows score, band, recommended action, rupee impact and reasons. |
| FR-16 | Shows a clear message on API failure or invalid input. |
| FR-17 | Shield members are visibly marked, and the recommendation for them defaults to "call", never "hold" (addresses Meenal's concern; decision recorded in the form). |

### 4.4 Evidence
| ID | Requirement |
|---|---|
| FR-18 | Report on the time-based validation set: AUC, PR-AUC, precision/recall at the chosen threshold, confusion matrix, calibration. |
| FR-19 | Compare against baselines: "never returns" (88.6% accuracy) and a simple COD-only rule. Show accuracy is uninformative here. |
| FR-20 | State **how often it is wrong**: false positives (good orders flagged) and false negatives (returns missed), in counts and rupees. |
| FR-21 | Show the leakage experiment: performance with vs without the service/pickup columns, to prove why they were removed. |
| FR-22 | Rupee analysis: net saving of strategies (do nothing / call top-k / call all / hold top-k) with sensitivity to the unknown margin-loss assumption. |
| FR-23 | Segment check: error and flag rates for Shield vs non-Shield, and by channel. |
| FR-24 | State the realistic expected score on test and why it may differ from validation (future period, shift, `INSTALL_BOOKED`). |

### 4.5 Deliverables
| ID | Requirement |
|---|---|
| FR-25 | **Memo** (one page, non-technical) covering: the decision, the number, the rupees, next week's action. Leads with the finding that 95% accuracy is not the right measure and what to use instead. |
| FR-26 | **Recording** ≤ 3 min: what was tried, changed, thrown away. No slides. |
| FR-27 | **submission-form.md** fully completed, including honest disclosure of AI tools used, cost, and what was discarded. |
| FR-28 | **README**: clean-machine setup and run steps, no paid key needed. |

---

## 5. Non-functional requirements

| ID | Category | Requirement |
|---|---|---|
| NFR-1 | Reproducibility | Fresh clone → install → run in a few commands. Pinned dependencies. Fixed random seeds. Trained model artifact included or rebuilt by one script. |
| NFR-2 | Cost | Zero per-order cost for core function (Finance requirement). Any optional API cost must be stated up front. |
| NFR-3 | Performance | Single prediction responds in under 1 second locally. |
| NFR-4 | Robustness | Starts without network or API key; degrades gracefully. |
| NFR-5 | Data handling | Policy §10: data stays within the engagement. **No upload to public repos**, so the repo must exclude CSVs or be private. |
| NFR-6 | Explainability | Reasons are readable by non-technical staff; no raw feature names or jargon. |
| NFR-7 | Honesty | All assumptions and decisions are written down with reasons. |

---

## 6. Decisions to record (unclear points in the brief)

| Question | Proposed decision | Why |
|---|---|---|
| Is 95% accuracy achievable or right? | Not the target. Report accuracy for context but optimise ranking and rupee value. | 88.6% is free; a 95% bar would need leakage. |
| Use service/pickup columns? | No. | They record the outcome or follow it; test does not contain them. |
| Hold or call? | Recommend calling high-risk non-Shield orders; hold only where numbers justify it. | Hold saves little and loses sales (12% cancel); call is Rs 45 for 35% prevention. |
| Shield customers | Never auto-hold; call at most. | High lifetime value; Ritu deferred it, but the cost of getting it wrong is large. |
| Return cost | Rs 1,150. | Finance's reported policy figure. |
| Margin lost on a cancelled hold | Unknown. Make it an explicit parameter and show sensitivity. | Not in the pack. |
| Bad order values | Repair/cap and flag. | Gateway issue flagged by Tanmay. |
| Metric for `predictions.csv` | Assume ranking-based. | A score, not a label, is requested. |

---

## 7. Pre-submission statement (to put in the form)
State a numeric expectation (e.g. AUC range) from time-based validation, adjusted downward for the future-period shift, plus the reasons. Fill this **before** sending.

---

## 8. Suggested architecture and stack

- **Model:** scikit-learn / LightGBM (or logistic regression as an interpretable baseline), with calibration.
- **API:** FastAPI (`/predict`, `/health`).
- **Screen:** single static HTML page served by the same app.
- **Reasons:** SHAP values or per-feature contributions mapped to plain-English templates.
- **Layout:** `data/` (gitignored), `train.py`, `app/`, `model/`, `notebooks or evidence/`, `memo.md`, `submission-form.md`, `README.md`, `requirements.txt`, `predictions.csv`.

---

## 9. Plan (time left: ~40 hours)

| Phase | Work | Time |
|---|---|---|
| 1 | Data audit, dedupe, cleaning, leakage proof | 3h |
| 2 | Features, baselines, time-based validation, model | 5h |
| 3 | Economics and threshold analysis, segment checks | 3h |
| 4 | `predictions.csv` and the pre-submission statement | 1h |
| 5 | API and screen, clean-machine test | 5h |
| 6 | Memo, form, recording | 4h |
| Buffer | Re-checks, README, final run | 3h |

---

## 10. Acceptance checklist
- [ ] `predictions.csv` has 2,096 unique `order_id`s with a numeric `score`
- [ ] No leaky features used; leakage experiment shown
- [ ] Time-based validation reported with error counts and rupee impact
- [ ] Endpoint returns score, action and plain-English reasons
- [ ] Screen works; app starts with no API key
- [ ] Memo is one page, non-technical, with decision, number, rupees, next steps
- [ ] Recording ≤ 3 minutes
- [ ] Form complete, with honest AI-tool disclosure
- [ ] No data pushed to a public repository
