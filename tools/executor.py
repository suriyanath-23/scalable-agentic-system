import json


def mock_network_executor(tool_name: str, method: str, url: str, **kwargs) -> str:
    """Simulates deterministic API calls for the PayPal scenario."""
    if tool_name == "paypal_check_dispute":
        user = str(kwargs.get("user_id", ""))
        if "123" in user:
            return json.dumps({
                "dispute_open": True,
                "dispute_id": "PP-DISP-99014",
                "claimant": "user_123",
                "dispute_amount": 50.00,
                "status": "REQUIRES_SELLER_ACTION"
            })
        return json.dumps({"dispute_open": False, "user_id": user, "status": "CLEAN"})

    if tool_name == "paypal_get_sales_volume":
        return json.dumps({
            "period": kwargs.get("period", "last_month"),
            "total_sales_volume": 128450.00,
            "currency": "USD",
            "settled_transactions": 412
        })

    if tool_name == "paypal_create_invoice":
        return json.dumps({
            "status": "SENT",
            "invoice_id": "INV-2026-0049",
            "recipient": kwargs.get("recipient") or kwargs.get("recipient_email"),
            "amount": kwargs.get("amount"),
            "currency": kwargs.get("currency", "USD")
        })

    return json.dumps({"status": "SUCCESS", "method": method, "endpoint": url, "payload": kwargs})