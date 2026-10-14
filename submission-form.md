# Submission Form: Kestrel Home Returns Risk (Variant A)

**Items only the author can fill (search for "FILL IN"):** repository link, recording link, the cost of each AI tool, and the model name Antigravity used.

## Author
- Name: Rajshekhar
- Email: pandeyrajshekhar690@gmail.com
- Role: Final-year B.E. Computer Engineering student, Government Engineering College, Modasa

## Links
- Repository (private, `data/` not committed): (https://github.com/RajshekharIslearning/Task2-banao)
- Screen recording (3 minutes or less): FILL IN

## Expected score and why (written before submitting)
The brief does not state the scoring metric. Assuming it ranks orders (AUC or similar), because a score is requested, I expect about **0.74 to 0.79, most likely 0.77**.

Basis: three rolling validation folds, each trained on the past and tested on the next three months, scored AUC 0.765, 0.773 and 0.788. The latest fold, April to June 2026, is closest to the test period.

Why the real score could be lower:
- The test orders (July to September 2026) are in the future, so customer behaviour may shift.
- 543 test orders carry an `INSTALL_BOOKED` status that never appears in training. The model does not use that column, but the mix of orders may differ.
- The return labels contain noise that no model can remove.

## What I built
- `predictions.csv`: a score for each of the 2,096 test orders, produced by `predict.py`. Reproduced byte-for-byte (SHA-256 starts 39993AB4).
- A logistic regression using only information available at dispatch (29 features), trained by `train.py`.
- A small service: `POST /predict` returns a score, a risk band, a recommended action (ship, call, or call with high priority), the estimated saving and plain-English reasons. `GET /health` reports status. One page (`app/static/index.html`) calls it.
- Evidence (`evidence/EVIDENCE.md`), rupee analysis (`evidence/02_economics.md`), a data audit, `DECISIONS.md`, a README, tests and a one-page memo to Ritu.

## What I tried, changed and threw away
- **Tried:** a cash-on-delivery-only baseline, logistic regression and gradient boosting.
- **Changed:** removed duplicates, repaired October 2025 order values, switched from random to time-based validation, and moved the target from accuracy to rupees.
- **Threw away:**
  - Any model using `last_service_event_type` or `pickup_scheduled_at`. It scored AUC 0.9989, but those columns record what happens after a return is decided and are absent from the test file.
  - Gradient boosting, which scored 0.0365 AUC lower on the last fold with the settings used.
  - A hold-first policy, which loses money once the profit lost per cancelled order exceeds about Rs 370 (or about Rs 545 under the other assumption).
  - Accuracy as the target. Predicting "never returned" is already about 88.5% accurate, because only about 1 in 9 orders is returned.

## AI tools used, what they cost, what I discarded
| Tool | Used for | Cost |
|---|---|---|
| Antigravity (model: [PASTE EXACT MODEL NAME shown in Antigravity, or MISSING]) | Writing and editing code, running tests, drafting evidence files | [E.g. "0 (free tier)" or "Rs 1,950 (Google AI Pro, one month)" or MISSING] |
| Claude (chat) | Planning, prompt writing, reviewing the agent's output, drafting the SRS and the memo | [E.g. "0 (free plan)" or "Rs 1,950 (Pro plan, one month)" or MISSING] |

Things I discarded or corrected from AI output:
- The agent attributed "never auto-hold Shield members" to Kestrel's policy. The policy says nothing about it, so I recorded it as my own decision.
- The first economics tables mislabelled "returns prevented" as "returns caught", giving wrong precision and recall. Fixed and recomputed.
- The agent's recommendation of holds for high-risk customers contradicted the economics. Changed to calls.
- The first evidence draft contained claims I could not trace (a wrong highest-risk channel, a made-up requirements table). I rewrote those sections from verified numbers.
- The agent weakened a clean-machine test by reusing installed packages. I rejected it and ran a real fresh-environment install myself.
- The agent started later deliverables out of order and its draft memo used unverified figures. I discarded that draft and rewrote the memo.

## Decisions where the brief was unclear
- **Which metric to target:** none was given, and accuracy is uninformative at an 11% return rate. I used ranking quality and rupees.
- **Duplicate orders (D-01):** 651 orders appear twice, once from the CRM and once from the partner feed, with identical contents. I kept the CRM row.
- **October 2025 values (D-02):** every order value that month was 100 times too high. I divided by 100.
- **Leaky columns:** `last_service_event_type` and `pickup_scheduled_at` excluded from every feature set.
- **Return cost:** Rs 1,150 (Finance), not Rs 600.
- **Calls over holds:** recommend phoning the riskiest 10 to 20% of orders, with a controlled test. Holds only avoid a return if the customer cancels, and they lose the sale.
- **Shield members (D-14):** never recommended for a hold. This is my decision, not Kestrel policy; the reason is that they are 22% of orders, 36% of returns and the highest-value customers.
- **Call threshold:** 0.112, where the expected saving from a call equals its Rs 45 cost.
- **Hidden metric:** assumed to be ranking-based.

## Known limits
- The 35% call effect comes from a small spring pilot with no control group. At 15% the quarterly saving falls from about Rs 36,000 to about Rs 4,500.
- The rupee analysis rests on one quarter of data with 245 returns.
- The profit lost on an order cancelled after a hold is not in the pack. The break-even is about Rs 370 or Rs 545 depending on the assumption.
- The test period is in the future, and `INSTALL_BOOKED` appears in test but never in training.
- About 28% of orders come from customers with no prior orders, so their risk rests on other signals.
- The screen was built and checked in basic form only. Response time was not measured.
- About 68% of the calls recommended would go to orders that would not have come back.

## How to run (PowerShell)
Put the 8 pack files into `data/` first (not committed).
```
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app/main.py
```
Then open http://127.0.0.1:8000 for the screen. In a second window:
```
Invoke-RestMethod http://127.0.0.1:8000/health
python -m pytest
python predict.py
python train.py
```
`predict.py` rewrites `predictions.csv`; `train.py` retrains and rewrites the model and metrics.
