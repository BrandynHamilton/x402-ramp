from stellar_sdk import Keypair, TransactionEnvelope, Network, Server, Asset, TransactionBuilder, Memo
import json
import requests
import toml
import os
from dotenv import load_dotenv
import webbrowser
import time
load_dotenv()

STELLAR_PRIVATE_KEY = os.getenv("THIRD_PARTY_STELLAR_KEY")  # Replace with your Stellar secret key

kp = Keypair.from_secret(STELLAR_PRIVATE_KEY)
server = Server(horizon_url="https://horizon-testnet.stellar.org")

def send_stellar_payment(recipient, amount, asset,memo=None):
    kp = Keypair.from_secret(STELLAR_PRIVATE_KEY)
    server = Server("https://horizon-testnet.stellar.org")
    acc = server.load_account(kp.public_key)

    tx = (
        TransactionBuilder(source_account=acc, network_passphrase=Network.TESTNET_NETWORK_PASSPHRASE, base_fee=100)
        .append_payment_op(destination=recipient, asset=asset, amount=str(amount))
    )
    if memo:
        tx.add_memo(Memo.id(int(memo)))

    tx = tx.build()
    tx.sign(kp)
    response = server.submit_transaction(tx)
    return response["hash"]

anchor_domain = "localhost:8080"  # Replace with your anchor's domain
toml_data = toml.loads(requests.get(f"http://{anchor_domain}/.well-known/stellar.toml").text)

print(json.dumps(toml_data, indent=2))

web_auth_endpoint = toml_data["WEB_AUTH_ENDPOINT"]
transfer_server = toml_data["TRANSFER_SERVER"]
signing_key = toml_data["SIGNING_KEY"]

print(f"web_auth_endpoint: {web_auth_endpoint}")
print(f"transfer_server: {transfer_server}")
print(f"signing_key: {signing_key}")

# Request challenge
challenge_tx = requests.get(web_auth_endpoint, params={"account": kp.public_key}).json()
envelope = TransactionEnvelope.from_xdr(challenge_tx["transaction"], Network.TESTNET_NETWORK_PASSPHRASE)

# Sign and send back
envelope.sign(kp)
resp = requests.post(web_auth_endpoint, json={"transaction": envelope.to_xdr()})
jwt_token = resp.json()["token"]

print(f"JWT Token: {jwt_token}")

headers = {"Content-Type": "application/json", "Authorization": f"Bearer {jwt_token}"}

withdraw_req = {
  "amount": "1",
  "asset_code": "USDC",
  "account": kp.public_key,
  "type": "ACH",
  "claimable_balance_supported": "false"
}

response = requests.get(
    f"http://{anchor_domain}/sep6/withdraw",
    headers=headers,
    params=withdraw_req
)
print(f"Response from withdraw request: {response.status_code}")
print(response.json())
breakpoint()
transaction_id = response.json()["id"]

tx_resp = requests.get(f"http://{anchor_domain}/sep6/transaction", headers=headers, params={"id": transaction_id})
tx_data = tx_resp.json().get("transaction", {})
print(f"Transaction data: {tx_data}")