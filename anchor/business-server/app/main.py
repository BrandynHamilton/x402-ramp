from fastapi import FastAPI, Request, Query
from pydantic import BaseModel
import os
from dotenv import load_dotenv
from stellar_sdk import Keypair
from x402.fastapi.middleware import require_payment

# Load environment variables from .env file
load_dotenv()

app = FastAPI()
app.middleware("http")(
    require_payment(price="0.01", pay_to_address="0x55D84680053B999fa3c452D82c5b2743B3AdD424",
                    path="/payments", network="base-sepolia")
)

@app.get("/")   
def read_root():
    return {"message": "Welcome to the Business Server API"}

@app.get("/payments")
def get_payments(request: Request):
    return {"message": "Payments endpoint"}

@app.get("/callbacks/health")
def health_check():
    return {"status": "ok"}

@app.get("/callbacks/price")
def get_price(
    context: str = Query(...),
    sell_asset: str = Query(...),
    buy_asset: str = Query(...),
    sell_amount: str = Query(...),
    buy_delivery_method: str = Query(...)
):
    return {
        "price": "1.00",
        "sell_amount": sell_amount,
        "buy_amount": sell_amount
    }

@app.get("/callbacks/rate")
def get_rate(
    type: str = Query(...),
    sell_asset: str = Query(...),
    sell_amount: float = Query(...),
    buy_asset: str = Query(...),
    buy_delivery_method: str = Query(...)
):
    price = 1.00
    fee_total = 0.00
    adjusted_sell_amount = sell_amount
    adjusted_buy_amount = sell_amount - fee_total

    return {
        "rate": {
            "id": "rate_id", 
            "price": str(price),  # required
            "sell_asset": sell_asset,  # required
            "buy_asset": buy_asset,  # required
            "sell_amount": str(adjusted_sell_amount),  # required
            "buy_amount": str(adjusted_buy_amount),    # required
            "fee": {
                "total": str(fee_total),  # required
                "asset": sell_asset,      # must be SEP-38 asset format (e.g. "stellar:USDC:...")
                "details": []             # optional but valid as empty list
            },
            "expires_at": "2025-12-01T00:00:00Z"  # optional for indicative
        }
    }

@app.post("/callbacks/transactions")
async def handle_transaction_callback(request: Request):
    body = await request.json()
    method = body.get("method")
    params = body.get("params", {})
    tx_id = params.get("transaction_id")

    print(f"Received callback method: {method} for transaction {tx_id}")

    if method == "request_onchain_funds":
        return {
            "jsonrpc": "2.0",
            "id": body["id"],
            "result": {
                "memo": "123456",
                "memo_type": "id",
                "destination_account": "GDHH5ISNXNLNMVW62GO45JAFRB2TATB5GINMVZ43TAAVC3BV3GYOTCJ6",
            }
        }

    elif method == "notify_onchain_funds_received":
        return {"jsonrpc": "2.0", "id": body["id"], "result": {"status": "ok"}}

    elif method == "notify_offchain_funds_sent":
        return {"jsonrpc": "2.0", "id": body["id"], "result": {"status": "sent"}}

    else:
        return {"jsonrpc": "2.0", "id": body["id"], "result": {"status": "ack"}}
