import requests, json
url='http://127.0.0.1:8001/predict'
payload={
    "order_id":"test-123",
    "customer_id":"CUST001",
    "sku":"SKU001",
    "order_placed_at":"2026-07-15 10:00:00",
    "payment_mode":"cod",
    "sales_channel":"web",
    "discount_pct":0.0,
    "qty":1,
    "order_value_inr":2500.50,
    "promised_delivery_days":3,
    "delivery_pincode":"411001",
    "delivery_note":None,
    "is_gift":"N",
    "customer_prior_orders":0,
    "customer_prior_returns":0
}
resp=requests.post(url, json=payload)
print('Status:', resp.status_code)
print('Response:', resp.text)
