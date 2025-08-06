import requests

payload = {
    "jsonrpc": "2.0",
    "id": "1",
    "method": "request_onchain_funds",
    "params": {
        "transaction_id": "some-transaction-id"
    }
}

response = requests.post("http://localhost:3000/callbacks/transactions", json=payload)
print(response.json())
