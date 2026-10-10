# Kestrel Returns - Pre-Dispatch Risk Scorer

## What this is
This internal tool provides a pre-dispatch risk model for evaluating the return probability of Kestrel customer orders. Non-technical operations staff can use this system to identify which orders should be shipped normally, called for confirmation, or reviewed.

## Requirements
- Python 3.10+ (tested on Python 3.13)
- Windows PowerShell (or standard Linux/macOS bash)
- Required CSVs in the `data/` directory (not stored in version control)

## Setup and Run Commands
The service runs locally with no paid keys and no external network access needed.

1. **Create and activate a virtual environment:**
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. **Install dependencies:**
   ```powershell
   pip install -r requirements.txt
   ```
   *(Tested in a fresh venv: succeeded with no errors)*

3. **Start the service:**
   ```powershell
   python app/main.py
   ```
   This starts a FastAPI web server on `http://127.0.0.1:8000`. You can visit that URL in a web browser for the visual interface.

## How to retrain the model
To train a fresh model from the latest `data/` CSV files:
```powershell
python train.py
```
This script handles missing values, prepares the dataset, and evaluates performance across 3 folds. The final model is automatically saved to `model/model.joblib`.

## How to regenerate predictions.csv
To produce `predictions.csv` for the unlabeled test data using the trained model:
```powershell
python predict.py
```
*(Reproduces predictions exactly, with SHA256 `39993AB454D0563C1675E047B85A5526EC666320CA486E834EAF4B5D822AE030`)*

## Folder Map
- `app/` - The API application and static web frontend.
- `data/` - Git-ignored folder containing necessary reference CSVs (customers, products, etc.).
- `docs/` & `evidence/` - Project documentation, economic analysis, data audits, and decision logs.
- `model/` - The serialized `model.joblib` artifact.
- `tests/` - The integration and unit test suite.
- `train.py` & `predict.py` - Core scripts for training and generating predictions.
- `validate.py` - Script for validating output formatting.

## Running Tests
Run the test suite using pytest to verify 6 of 6 tests pass:
```powershell
python -m pytest
```

To run the 11 live validation checks against a running server:
```powershell
python validate.py --live http://127.0.0.1:8000
```
*(Tested successfully against the live server)*

## Sample cURL Request
You can manually score an order using the API:
```bash
curl -X POST http://127.0.0.1:8000/predict `
  -H "Content-Type: application/json" `
  -d '{
    "order_id": "KO2610504",
    "customer_id": "KC105196",
    "sku": "KH-IC-03",
    "order_placed_at": "2026-07-01 00:51:00",
    "payment_mode": "prepaid_upi",
    "sales_channel": "web",
    "discount_pct": 13,
    "qty": 1,
    "order_value_inr": 3521.76,
    "promised_delivery_days": 7,
    "delivery_pincode": "440378",
    "delivery_note": "Office address, weekdays only",
    "is_gift": "N",
    "customer_prior_orders": 2,
    "customer_prior_returns": 1
}'
```

## Known Limits
- **Data Dependency:** If the `data/` folder is missing, the API handles it gracefully. `GET /samples` shows a polite message, and `POST /predict` returns a `503 Service Unavailable` with `reference data not found; copy the CSVs into data/`.
- **Unknown Entities:** If a SKU or customer is not found in the reference tables, the model falls back to default values but flags a visible warning that risk may be understated.
- **Leaky Features:** Fields like `last_service_event_type` and `pickup_scheduled_at` are automatically ignored to prevent data leakage.
