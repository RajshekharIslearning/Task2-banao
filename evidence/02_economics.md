# Economic Analysis (Fold 3 Holdout)

**Reason for updating order count**: The prior analysis used a test end date of 2026-06-30 00:00:00, which dropped June 30 orders. This report uses 2026-06-30 23:59:59 exactly matching `train.py` Fold 3 (2,126 orders).

## Call Policies
| Policy | flagged_orders | returns_caught | returns_prevented | false_alarms | missed_returns | returns_remaining | precision | recall | accuracy | net_rupees |
|--------|----------------|----------------|-------------------|--------------|----------------|-------------------|-----------|--------|----------|------------|
| Do nothing | 0 | 0 | 0.0 | 0 | 245 | 245.0 | 0.000 | 0.000 | 0.885 | 0.0 |
| Call everyone | 2126 | 245 | 85.8 | 1881 | 0 | 159.2 | 0.115 | 1.000 | 0.115 | 2942.5 |
| Call above break-even (> 0.112) | 658 | 167 | 58.4 | 491 | 78 | 186.6 | 0.254 | 0.682 | 0.732 | 37607.5 |
| Call top 10% | 213 | 92 | 32.2 | 121 | 153 | 212.8 | 0.432 | 0.376 | 0.871 | 27445.0 |
| Call top 20% | 426 | 137 | 47.9 | 289 | 108 | 197.1 | 0.322 | 0.559 | 0.813 | 35972.5 |
| Call top 30% | 638 | 165 | 57.7 | 473 | 80 | 187.2 | 0.259 | 0.673 | 0.740 | 37702.5 |

## Hold Policies (Sensitivity to Margin Loss)
| Policy | Margin 0 | Margin 300 | Margin 600 | Margin 1000 | Margin 1500 |
|--------|----------|------------|------------|-------------|-------------|
| Hold top 10% | 12696.0 | 5028.0 | -2640.0 | -12864.0 | -25644.0 |
| Hold top 20% | 18906.0 | 3570.0 | -11766.0 | -32214.0 | -57774.0 |
| Hold top 30% | 22770.0 | -198.0 | -23166.0 | -53790.0 | -92070.0 |

## Exact Hold Formula and Break-even
A hold causes 12% of held orders to cancel. We assume these cancellations would have been returned.
Savings = True Positives * 0.12 * Rs 1,150.
Cost (Margin Loss) depends on assumptions:
- **Assumption A** (margin lost on every cancelled held order): Break-even margin = (TP / Total Held) * 1150 = Rs 369.8
- **Assumption B** (margin lost only on cancelled false alarms): Break-even margin = (TP / FP) * 1150 = Rs 545.2

## Call Policies Sensitivity to Effectiveness
| Policy | Net Rs (15% effect) | Net Rs (25% effect) | Net Rs (35% effect) |
|--------|----------------------|----------------------|----------------------|
| Call top 10% | 6,285 | 16,865 | 27,445 |
| Call top 20% | 4,462 | 20,218 | 35,972 |
| Call > BE | -802 | 18,402 | 37,608 |

Top 20% Policy 90% Confidence Interval (1000 bootstraps): Rs 28,953 to Rs 42,424

## Shield vs Non-Shield
- Shield return rate: 20.5% (AUC: 0.765)
- Non-Shield return rate: 8.9% (AUC: 0.768)
- Holding Shield top 20% saves Rs 10074.0 (assuming 0 margin loss). Given their LTV, holding Shield is unprofitable.

## Baseline
- **Total return cost with no action**: Rs 281,750 (245 returns x Rs 1,150)
- **Share recovered by recommended policy**: 13.3%

![Economics Chart](economics_chart.png)

## Recommendation
This holdout represents one quarter containing 245 actual returns. The analysis shows that net savings are highly sensitive to the true effectiveness of the confirmation call, which currently relies on an unverified 35% estimate from a small pilot without a control group. 

While calling all orders above the break-even probability (11.2%) yields the highest theoretical net saving at a 35% effectiveness (Rs 37,608), it is also the most exposed to a shortfall in that effectiveness (dropping to Rs -802 at 15%). 

We strongly recommend **starting with the top 10% to 20%** most risky orders. Crucially, this rollout must include a **controlled pilot** (a randomized holdout group that is not called despite being flagged) to precisely measure the true effectiveness of the call. Once the true lift is known, the threshold can be expanded. 

We strongly advise against a blanket **Hold** policy. Because a hold causes 12% of customers to cancel, we lose the margin on those sales. Our analysis shows that if the margin lost is greater than Rs 370 (Assumption A), holding loses money compared to doing nothing.
