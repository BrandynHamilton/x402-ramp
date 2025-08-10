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

anchor_domain = "testanchor.stellar.org"  # Replace with your anchor's domain
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

# r = requests.get("http://localhost:8080/info", headers=headers)
# r.raise_for_status()
# print(r.json())

# breakpoint()

r = requests.get(f"http://{anchor_domain}/sep38/info")
r.raise_for_status()
print(r.json())

assets = r.json()["assets"]
print("Available assets:")
for asset in assets:
    print(f"- {asset['asset']}")
    if asset.get('asset')== 'stellar:USDC:GBBD47IF6LWK7P7MDEVSCWR7DPUWV3NY3DTQEVFL4NAT4AQH3ZLLFLA5':
        source_asset = asset['asset']
        asset_code, issuer = source_asset.split(':')[1:3]
        print(f"Asset code: {asset_code}, Issuer: {issuer}")
        usdc_asset = Asset(asset_code, issuer)
        print(f"Using asset: {usdc_asset.code} issued by {usdc_asset.issuer}")
    else:
        destination_asset = asset['asset']
    
# transfer_server = f"http://{anchor_domain}/sep24"  


params = {
    "context": "sep6",
    "sell_asset": "stellar:USDC:GBBD47IF6LWK7P7MDEVSCWR7DPUWV3NY3DTQEVFL4NAT4AQH3ZLLFLA5",
    "buy_asset": "iso4217:USD",
    "sell_amount": "1",
    "buy_delivery_method": "WIRE"
}

r = requests.get(f"http://{anchor_domain}/sep38/price", params=params, headers=headers)
r.raise_for_status()
print(f"Price response: {r.json()}")
breakpoint()

params = {
  "sell_asset": "stellar:USDC:GBBD47IF6LWK7P7MDEVSCWR7DPUWV3NY3DTQEVFL4NAT4AQH3ZLLFLA5",
  "buy_asset": "iso4217:USD",
  "sell_amount": "1",
  "buy_delivery_method": "WIRE",
  "context": "sep6"
}

r = requests.post(f"http://{anchor_domain}/sep38/quote", json=params, headers=headers)
r.raise_for_status()
print(f"Rate response: {r.json()}")

breakpoint()

data = r.json()
id = data["id"]
print(f"Transaction ID: {id}")

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
print(response.json())
breakpoint()
transaction_id = response.json()["id"]

tx_resp = requests.get(f"http://{anchor_domain}/sep6/transaction", headers=headers, params={"id": transaction_id})
tx_data = tx_resp.json().get("transaction", {})
print(f"Transaction data: {tx_data}")

breakpoint()

payload = {
    "jsonrpc": "2.0",
    "id": "1",
    "method": "request_onchain_funds",
    "params": {
        "transaction_id": transaction_id
    }
}

response = requests.post("http://localhost:3000/callbacks/transactions", json=payload)
print(response.json())

# breakpoint()

tx_data = response.json().get("result", {})
    
memo = tx_data.get("memo")
memo_type = tx_data.get("memo_type")
destination = tx_data.get("destination_account")
status = tx_data.get("status")

if memo and destination:
    print(f"Got payment info! Destination: {destination}, Memo: {memo} ({memo_type})")
    
elif status == "error":
    raise Exception("Withdrawal failed")
else:
    print("Waiting for anchor to provide payment info...")
    time.sleep(2)

# breakpoint()

stellar_tx = send_stellar_payment(recipient=destination, amount=1, asset=usdc_asset, memo=memo)
print(f"Stellar transaction sent: {stellar_tx}")

while True:
    tx_resp = requests.get(f"http://{anchor_domain}/sep6/transaction", headers=headers, params={"id": transaction_id})
    status = tx_resp.json().get("transaction", {}).get("status")
    if status == "completed":
        print("Withdrawal complete!")
        break
    elif status == "error":
        raise Exception("Withdrawal failed")
    else:
        print(f"Waiting for completion, status: {status}")
        time.sleep(3)