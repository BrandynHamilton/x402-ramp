import requests
import time
from stellar_sdk import Keypair, Server, Network, TransactionBuilder, Asset, TransactionEnvelope
import os
from dotenv import load_dotenv
load_dotenv()

# 1. CONFIG
anchor_domain = "localhost:8080"
callback_server = "http://localhost:3000"
web_auth_endpoint = f"http://{anchor_domain}/auth"
transaction_endpoint = f"http://{anchor_domain}/sep24/transaction"
withdraw_endpoint = f"http://{anchor_domain}/sep24/transactions/withdraw/interactive"

# 2. YOUR TESTNET ACCOUNT
STELLAR_PRIVATE_KEY = os.getenv('THIRD_PARTY_STELLAR_KEY')
kp = Keypair.from_secret(STELLAR_PRIVATE_KEY)
stellar_address = kp.public_key
usdc_asset = Asset("USDC", "GBBD47IF6LWK7P7MDEVSCWR7DPUWV3NY3DTQEVFL4NAT4AQH3ZLLFLA5")  # Replace if needed

# 3. HORIZON SETUP
server = Server(horizon_url="https://horizon-testnet.stellar.org")
account = server.load_account(stellar_address)

# 4. SEP-10 AUTH
challenge_tx = requests.get(web_auth_endpoint, params={"account": kp.public_key}).json()
envelope = TransactionEnvelope.from_xdr(challenge_tx["transaction"], Network.TESTNET_NETWORK_PASSPHRASE)
envelope.sign(kp)
resp = requests.post(web_auth_endpoint, json={"transaction": envelope.to_xdr()})
jwt_token = resp.json()["token"]
headers = {"Authorization": f"Bearer {jwt_token}"}

customer_endpoint = f"http://{anchor_domain}/customer"
customer_data = {
    "account": stellar_address,
    "type": "individual",
    "first_name": "Test",
    "last_name": "User",
    "email_address": "testuser@example.com"
    # Add more fields if your anchor requires them (e.g., "bank_account", "id_type", etc.)
}
resp = requests.put(customer_endpoint, headers=headers, json=customer_data)
print("👤 KYC response:", resp.json())

# 5. NON-INTERACTIVE WITHDRAW INIT
withdraw_req = {
    "asset_code": "USDC",
    "account": stellar_address,
    "amount": "1",
    "type": "bank_account",
    "dest": "1234567890",  # placeholder - use a valid identifier for Panamanian bank account
    "dest_extra": "Banco General, Panama",
    "lang": "en",
    "claimable_balance_supported": "false"
}
response = requests.post(withdraw_endpoint, headers=headers, json=withdraw_req)
response.raise_for_status()
data = response.json()
transaction_id = data["id"]

print(f"💸 Non-interactive withdrawal initiated: {transaction_id}")

# 6. WAIT FOR "pending_user_transfer_start" STATUS
while True:
    tx_resp = requests.get(transaction_endpoint, headers=headers, params={"id": transaction_id})
    tx_data = tx_resp.json()["transaction"]
    status = tx_data["status"]
    print(f"Status: {status}")

    if status == "pending_user_transfer_start":
        # Now send the Stellar payment to anchor
        destination = tx_data["stellar_account"]
        memo = tx_data["withdraw_memo"]
        memo_type = tx_data["withdraw_memo_type"]

        builder = TransactionBuilder(
            source_account=account,
            network_passphrase=Network.TESTNET_NETWORK_PASSPHRASE,
            base_fee=100
        ).append_payment_op(
            destination=destination,
            amount="1",
            asset=usdc_asset,
        ).set_timeout(60)

        # Add memo depending on type
        if memo_type == "text":
            builder.add_text_memo(memo)
        elif memo_type == "id":
            builder.add_memo_id(int(memo))
        elif memo_type == "hash":
            builder.add_memo_hash(bytes.fromhex(memo))

        tx = builder.build()
        tx.sign(kp)
        resp = server.submit_transaction(tx)
        print("✅ Sent payment:", resp["hash"])
        break

    elif status in ["completed", "error"]:
        print("⚠️ Unexpected status:", status)
        break

    time.sleep(5)

# 7. FINAL STATUS POLL (UNTIL COMPLETE)
while True:
    tx_resp = requests.get(transaction_endpoint, headers=headers, params={"id": transaction_id})
    tx_data = tx_resp.json()["transaction"]
    print(f"Status: {tx_data['status']}")

    if tx_data["status"] == "completed":
        print("✅ Withdrawal complete: funds sent to bank")
        break
    elif tx_data["status"] == "error":
        print("❌ Error during withdrawal:", tx_data["message"])
        break

    time.sleep(5)

# 8. (OPTIONAL) SIMULATE FIAT PAYOUT IF USING CALLBACK SERVER
if tx_data["status"] != "completed":
    payload = {
        "jsonrpc": "2.0",
        "id": "1",
        "method": "simulate_outgoing_transfer",
        "params": {
            "transaction_id": transaction_id
        }
    }
    r = requests.post(f"{callback_server}/callbacks/transactions", json=payload)
    print("📦 Simulated fiat payout:", r.json())

# 9. FINAL CONFIRMATION
final_resp = requests.get(transaction_endpoint, headers=headers, params={"id": transaction_id})
final_data = final_resp.json()["transaction"]
print("✅ Final status:", final_data["status"])
