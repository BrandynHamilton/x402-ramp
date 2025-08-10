from fastapi import FastAPI, Request, Query, BackgroundTasks, HTTPException, Path
from pydantic import BaseModel
import os
from dotenv import load_dotenv
from stellar_sdk import Keypair, Server
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from x402.fastapi.middleware import require_payment

# Load environment variables from .env file
load_dotenv()

server = Server("https://horizon-testnet.stellar.org")

STELLAR_PRIVATE_KEY = os.getenv("STELLAR_PRIVATE_KEY")
server = Server(horizon_url="https://horizon-testnet.stellar.org")
stellar_kp = Keypair.from_secret(STELLAR_PRIVATE_KEY)

async def monitor_transfer_and_bridge(req, id):
    print(f"Background task started for request: {req}")

    print(f"🔁 Watching for USDC on Stellar...")

    seen = set()
    for payment in server.payments().for_account(stellar_kp.public_key).cursor("now").stream():
        print(f'🔍 Checking payment: {payment}')
        if payment["type"] == "payment" and \
            payment["to"] == stellar_kp.public_key and \
            payment["id"] not in seen:

            seen.add(payment["id"])
            print(f"✅ Stellar Payment detected: {payment}")
            db[id] = {"status": "completed"}
            break

app = FastAPI()
app.middleware("http")(
    require_payment(price="0.01", pay_to_address="0x55D84680053B999fa3c452D82c5b2743B3AdD424",
                    path="/payments", network="base-sepolia")
)

# In-memory databases
db_customers = {}  # key: customer_id, value: customer data and status
db_events = {}  # key: event_id, value: event data
db_rates = {}  # Optionally cache rates if needed
db = {}

# Models for clarity
class Customer(BaseModel):
    id: str
    status: Optional[str] = "pending"
    kyc_fields: Optional[Dict[str, Any]] = None
    # Add any other KYC related fields as needed

class RateFee(BaseModel):
    total: str
    asset: str
    details: List[Any] = []

class RateResponse(BaseModel):
    id: str
    price: str
    sell_asset: str
    buy_asset: str
    sell_amount: str
    buy_amount: str
    fee: RateFee
    expires_at: Optional[str] = None

@app.get("/")   
def read_root():
    return {"message": "Welcome to the Business Server API"}

@app.get("/payments")
def get_payments(request: Request):
    return {"message": "Payments endpoint"}

# @app.get("/transactions/status/{transaction_id}")
# def get_transaction_status(transaction_id: str):
#     status = db.get(transaction_id, {"status": "unknown"})
#     return {"transaction_id": transaction_id, "status": status["status"]}

@app.get("/callbacks/health")
def health_check():
    return {"status": "ok"}

@app.get("/callbacks/customer")
async def get_customer(
    id: Optional[str] = Query(None, description="Customer ID to lookup"),
):
    """
    Return required KYC fields if customer not found,
    or return existing customer status.
    """
    if not id:
        # No ID, return required KYC fields for new customer
        required_fields = {
            "first_name": {"type": "string", "description": "Customer first name"},
            "last_name": {"type": "string", "description": "Customer last name"},
            "email_address": {"type": "string", "description": "Customer email"},
            # Add additional KYC required fields as per your policy
        }
        return {
            "fields": required_fields
        }

    customer = db_customers.get(id)
    if not customer:
        # Return fields required if not found
        return {
            "fields": {
                "id": {"type": "string"},
                "first_name": {"type": "string"},
                "last_name": {"type": "string"},
                "email_address": {"type": "string"},
            }
        }

    return {
        "id": customer["id"],
        "status": customer.get("status", "pending"),
        "message": customer.get("message", "")
    }


@app.put("/callbacks/customer")
async def put_customer(data: dict):
    """
    Create or update customer info.
    Validate and store the data, respond with customer id.
    """
    customer_id = data.get("id")
    if not customer_id:
        raise HTTPException(status_code=400, detail="Missing 'id' field in customer data")

    # You can add validation logic here or rely on external KYC
    db_customers[customer_id] = {
        "id": customer_id,
        "status": "pending",
        "data": data  # Store all submitted data
    }

    return {"id": customer_id, "status": "pending"}


@app.delete("/callbacks/customer/{customer_id}")
async def delete_customer(customer_id: str = Path(...)):
    """
    Delete customer data if exists.
    """
    if customer_id not in db_customers:
        raise HTTPException(status_code=404, detail="Customer not found")
    del db_customers[customer_id]
    return {"status": "deleted", "id": customer_id}

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

@app.post("/callbacks/event")
async def post_event(event: dict):
    """
    Receive event notifications such as transaction or quote status changes.
    """
    event_id = event.get("id")
    event_type = event.get("type")

    if not event_id or not event_type:
        raise HTTPException(status_code=400, detail="Missing event 'id' or 'type'")

    # Store or update event in DB
    db_events[event_id] = event

    # Your business logic here:
    # e.g., update records, notify downstream, etc.

    return {"status": "received", "id": event_id, "type": event_type}

@app.get("/callbacks/rate")
async def get_rate(
    sell_asset: str = Query(...),
    buy_asset: str = Query(...),
    sell_amount: Optional[float] = Query(None),
    buy_amount: Optional[float] = Query(None),
    buy_delivery_method: Optional[str] = Query(None),
    client_id: Optional[str] = Query(None),
):
    """
    Provide exchange rate, either indicative or firm.
    Must accept either sell_amount or buy_amount but not both.
    """
    if sell_amount and buy_amount:
        raise HTTPException(status_code=400, detail="Only one of sell_amount or buy_amount can be specified")

    # Example fixed price and fee, adapt to your logic
    price = 1.00
    fee_total = 0.00

    amount = sell_amount if sell_amount else (buy_amount if buy_amount else 0)
    adjusted_sell_amount = amount
    adjusted_buy_amount = amount - fee_total

    rate_id = "rate123"
    expires_at = "2025-12-01T00:00:00Z"

    fee = {
        "total": f"{fee_total:.2f}",
        "asset": sell_asset,
        "details": []
    }

    return {
        "rate": {
            "id": rate_id,
            "price": f"{price:.2f}",
            "sell_asset": sell_asset,
            "buy_asset": buy_asset,
            "sell_amount": f"{adjusted_sell_amount:.2f}",
            "buy_amount": f"{adjusted_buy_amount:.2f}",
            "fee": fee,
            "expires_at": expires_at
        }
    }

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

@app.post("/callbacks/transactions")
async def handle_transaction_callback(request: Request, background_tasks: BackgroundTasks):
    body = await request.json()

    method = body.get("method")
    params = body.get("params", {})
    tx_id = params.get("transaction_id") or body.get("id")

    if not tx_id:
        return {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32602, "message": "Missing transaction_id"}
        }

    # Retrieve existing status or default
    status = db.get(tx_id, {"status": "unknown"})['status']
    print(f"Transaction {tx_id} status: {status}")

    print(f"Received callback method: {method} for transaction {tx_id}")

    if method == "request_onchain_funds":
        # Mark transaction as funds requested
        db[tx_id] = {"status": "funds_requested"}
        # Start background task to monitor Stellar for funds
        background_tasks.add_task(monitor_transfer_and_bridge, request, tx_id)
        return {
            "jsonrpc": "2.0",
            "id": tx_id,
            "result": {
                "memo": "id",  # Typically a memo or identifier for Stellar payment
                "memo_type": "id",  # Memo type, e.g., id, text, hash
                "destination_account": stellar_kp.public_key,  # Your Stellar account to receive funds
                "status": "funds_requested"
            }
        }

    elif method == "notify_onchain_funds_received":
        # You might update status to 'funds_received'
        db[tx_id] = {"status": "funds_received"}
        return {
            "jsonrpc": "2.0",
            "id": tx_id,
            "result": {"status": "funds_received"}
        }

    elif method == "notify_offchain_funds_sent":
        # Mark that offchain funds have been sent
        db[tx_id] = {"status": "offchain_funds_sent"}
        return {
            "jsonrpc": "2.0",
            "id": tx_id,
            "result": {"status": "offchain_funds_sent"}
        }

    else:
        # Default fallback returns current status
        return {
            "jsonrpc": "2.0",
            "id": tx_id,
            "result": {"status": status}
        }