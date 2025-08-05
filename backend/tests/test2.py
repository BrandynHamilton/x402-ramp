from json import load
import stat
from stellar_sdk import Account, Server, Asset, Keypair, Network, TransactionBuilder
import os
from dotenv import load_dotenv
import requests
import time
load_dotenv()

STELLAR_PRIVATE_KEY = os.getenv("STELLAR_PRIVATE_KEY")
TARGET_ADDRESS = os.getenv("TARGET_ADDRESS", "0x38979DFdB5d8FD76FAD4E797c4660e20015C6a84")

def send_stellar_payment(recipient, amount, memo=None):
    kp = Keypair.from_secret(STELLAR_PRIVATE_KEY)
    server = Server("https://horizon-testnet.stellar.org")
    acc = server.load_account(kp.public_key)

    tx = (
        TransactionBuilder(source_account=acc, network_passphrase=Network.TESTNET_NETWORK_PASSPHRASE, base_fee=100)
        .append_payment_op(destination=recipient, asset=usdc_asset, amount=str(amount))
    )
    if memo:
        tx.add_text_memo(memo)

    tx = tx.build()
    tx.sign(kp)
    response = server.submit_transaction(tx)
    return response["hash"]

server = Server(horizon_url="https://horizon-testnet.stellar.org")
stellar_kp = Keypair.from_secret(STELLAR_PRIVATE_KEY)
bridge_account = server.load_account(stellar_kp.public_key)
STELLAR_ADDRESS = stellar_kp.public_key
STELLAR_TESTNET_USD_ISSUER = os.getenv("STELLAR_TESTNET_USD_ISSUER", "GBBD47IF6LWK7P7MDEVSCWR7DPUWV3NY3DTQEVFL4NAT4AQH3ZLLFLA5")
usdc_asset_code = "USDC"
usdc_asset = Asset(usdc_asset_code, STELLAR_TESTNET_USD_ISSUER)  # Circle testnet issuer
amount = 1

request_data = {
    "apikey": "",
    "target_address": TARGET_ADDRESS, # Example Ethereum address
    "source_address": stellar_kp.public_key,  # Example Stellar address
    "target_chain": "base-sepolia", 
    "amount": amount
}

print("Requesting bridge for amount:", amount, "from", stellar_kp.public_key, "to", TARGET_ADDRESS)

r = requests.post("http://localhost:9000/bridge/request", json=request_data)
r.raise_for_status()
print("Bridge request sent successfully:", r.json())
data = r.json()

status = data.get("status")

if status != "watching for source transfer":
    raise Exception(f"Unexpected status: {status}")

request_id = data.get("request_id")
bridge_address = data.get("bridge_address")

stellar_tx = send_stellar_payment(bridge_address, amount, memo=f"Bridge from {stellar_kp.public_key[0:4]}")

for _ in range(10):
    try:
        r = requests.get(f"http://localhost:9000/bridge/status/{request_id}")
        r.raise_for_status()
        status = r.json().get("status")
        if status == "completed":
            print("Bridge transfer completed successfully.")
            print("Bridge transaction details:", r.json())
            break
    except requests.RequestException as e:
        print(f"Error checking status: {e}")
    time.sleep(5)
