from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import httpx
from stellar_sdk import Keypair, TransactionEnvelope, Network, Server, Asset, TransactionBuilder, Memo
from web3 import Web3
import os
import toml
from dotenv import load_dotenv
import json
import requests
import time
load_dotenv()
current_dir = os.path.dirname(os.path.abspath(__file__))

ANCHOR_TOML = "https://testanchor.stellar.org/.well-known/stellar.toml"
HOME_DOMAIN = "testanchor.stellar.org"
ASSET_CODE = "USDC"  # or "USDT", etc.

STELLAR_PRIVATE_KEY = os.getenv("BRIDGE_STELLAR_PRIVATE_KEY")

server = Server(horizon_url="https://horizon-testnet.stellar.org")
kp = Keypair.from_secret(STELLAR_PRIVATE_KEY)
stellar_account = server.load_account(kp.public_key)
STELLAR_ADDRESS = kp.public_key
STELLAR_TESTNET_USD_ISSUER = os.getenv("STELLAR_TESTNET_USD_ISSUER", "GBBD47IF6LWK7P7MDEVSCWR7DPUWV3NY3DTQEVFL4NAT4AQH3ZLLFLA5")
usdc_asset_code = "USDC"
usdc_asset = Asset(usdc_asset_code, STELLAR_TESTNET_USD_ISSUER)  # Circle testnet issuer

infura_key = os.getenv("INFURA_API_KEY")
WEB3_PROVIDER = f"https://base-sepolia.infura.io/v3/{infura_key}"  # or local/testnet
USDC_ADDRESS = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"  # USDC on Base Sepolia
print(F'current_dir: {current_dir}')
abi_path = os.path.join(current_dir, "abi", "erc20_abi.json")
print(F'abi_path: {abi_path}')
EVM_PRIVATE_KEY = os.getenv("THIRD_PARTY_EVM_KEY")

with open(abi_path, "r") as abi_file:
    ERC20_ABI = abi_file.read()

w3 = Web3(Web3.HTTPProvider(WEB3_PROVIDER))
evm_account = w3.eth.account.from_key(EVM_PRIVATE_KEY)
usdc_contract = w3.eth.contract(address=USDC_ADDRESS, abi=ERC20_ABI)
EVM_ADDRESS = evm_account.address
w3.eth.default_account = EVM_ADDRESS

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

app = FastAPI()
templates = Jinja2Templates(directory="templates")

@app.get("/")
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/bridge")
async def bridge(request: Request, amount: float):
    request_data = {
        "apikey": "",
        "stellar_address": STELLAR_ADDRESS, # Example Ethereum address
        "evm_address": EVM_ADDRESS,  # Example Stellar address
        "target_chain": "stellar-testnet", 
        "amount": amount
    }

    r = requests.post("http://localhost:9000/bridge/request", json=request_data)
    r.raise_for_status()
    print("Bridge request sent successfully:", r.json())
    data = r.json()

    status = data.get("status")

    if status != "watching for source transfer":
        return {"error": f"Unexpected status: {status}"}

    request_id = data.get("request_id")
    bridge_address = data.get("bridge_address")

    stellar_tx = send_stellar_payment(bridge_address, amount, memo=f"Bridge from {kp.public_key[0:4]}")

    for _ in range(10):
        try:
            r = requests.get(f"http://localhost:9000/bridge/status/{request_id}")
            r.raise_for_status()
            status = r.json().get("status")
            if status == "completed":
                message = f"Bridge transaction details: {r.json()}"
                return {"message": message, "stellar_tx": stellar_tx}
        except requests.RequestException as e:
            print(f"Error checking status: {e}")
        time.sleep(5)


@app.get("/withdraw")
async def withdrawal_ui(request: Request, amount: float):
    anchor_domain = "localhost:8080"  # Replace with your anchor's domain
    toml_data = toml.loads(requests.get(f"http://{anchor_domain}/.well-known/stellar.toml").text)

    print(json.dumps(toml_data, indent=2))

    amount_str = str(amount)
    if amount_str.endswith(".0"):
        amount_str = amount_str[:-2]

    final_resp = {}

    web_auth_endpoint = toml_data["WEB_AUTH_ENDPOINT"]
    transfer_server = toml_data["TRANSFER_SERVER"]
    signing_key = toml_data["SIGNING_KEY"]

    # Request challenge
    challenge_tx = requests.get(web_auth_endpoint, params={"account": kp.public_key}).json()
    envelope = TransactionEnvelope.from_xdr(challenge_tx["transaction"], Network.TESTNET_NETWORK_PASSPHRASE)

    # Sign and send back
    envelope.sign(kp)
    resp = requests.post(web_auth_endpoint, json={"transaction": envelope.to_xdr()})
    jwt_token = resp.json()["token"]

    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {jwt_token}"}

    withdraw_req = {
        "amount": amount_str,
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

    final_resp = {
        "message": "Withdrawal request processed successfully",
        "stellar_tx": stellar_tx,
        "transaction_id": transaction_id,
        "destination": destination,
        "memo": memo,
        "status": status,
        "amount": amount
    }

