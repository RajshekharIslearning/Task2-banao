# Memo: Pre-Dispatch Returns Risk Model

**To:** Ritu Deshpande, Head of D2C Operations
**From:** Banao Model Build Team
**Date:** October 9, 2026
**Subject:** Return Risk Model Delivery & Strategic Recommendations

### 1. Reframing the Target: Why 95% Accuracy is the Wrong Goal
We reviewed the request for a model with 95% accuracy. However, our baseline data shows that only ~11.4% of orders are returned. This means a model that simply predicts "No order will ever be returned" achieves an 88.6% accuracy but provides zero business value. To hit 95%, a model would have to rely on "leaky" data—like picking up the fact that a reverse pickup has *already* been scheduled (which we proved pushes accuracy to 99%, but only *after* the return is approved).

Instead of raw accuracy, we built this model to optimize **Rupee Value Saved**. The goal is to accurately rank orders from most-risky to least-risky at the moment of dispatch, and apply the most cost-effective action.

### 2. The Real Cost of "Holding" an Order
We analyzed the financial impact using Farhan's figure of Rs 1,150 per return. We ran scenarios based on the pilot data:
- **Calling a customer:** Costs Rs 45 and prevents ~35% of returns.
- **Holding an order:** Saves the return cost (Rs 1,150) but results in 12% of those customers cancelling their order entirely, losing us the profit margin on those sales.

**The Finding:** Holding orders is a net loss. On a typical week's volume of 2,100 orders, holding the riskiest 20% of orders *loses* us ~Rs 6,000 because the cost of lost sales outweighs the shipping savings. Conversely, calling those exact same riskiest 20% of orders yields a net **savings of ~Rs 36,700**. 

### 3. Our Decision and Next Week's Action
Based on the economics, we have decided to **not automatically hold any orders**. Instead, the model flags high-risk orders to be routed to the Service Desk for a pre-dispatch confirmation call.

Furthermore, following Meenal's feedback, the system explicitly identifies **Shield customers**. High-risk Shield orders will be flagged for a gentle confirmation call rather than any aggressive intervention, preserving their customer experience.

**Next Week's Action Plan:**
1. **Deploy the scoring API:** The warehouse system will ping our new API at dispatch.
2. **Route to Call Center:** The riskiest top 20% of non-Shield orders (which account for a disproportionate amount of returns) will be routed to the Service Desk for the Rs 45 confirmation call.
3. **Monitor Margins:** We need Finance to confirm the exact average margin lost on a cancelled order to fine-tune the thresholds. For now, the model provides a safe, profitable starting point.
