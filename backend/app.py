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

STELLAR_PRIVATE_KEY = os.getenv("THIRD_PARTY_STELLAR_KEY")

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

stellar_base_url = "https://testnet.stellarchain.io/transactions/"
base_base_url = "https://sepolia.basescan.org/tx/"

def get_stellar_usdc_balance(public_key: str) -> float:
    account = server.accounts().account_id(public_key).call()
    for balance in account["balances"]:
        if balance.get("asset_code") == "USDC" and balance.get("asset_issuer") == STELLAR_TESTNET_USD_ISSUER:
            return float(balance["balance"])
    return 0.0

def get_evm_usdc_balance(address: str) -> float:
    decimals = usdc_contract.functions.decimals().call()
    raw_balance = usdc_contract.functions.balanceOf(Web3.to_checksum_address(address)).call()
    return raw_balance / (10 ** decimals)

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

def get_dynamic_gas_fees(
    w3,
    default_priority_gwei: float = 2,
    history_blocks: int = 5,
    reward_pct: int = 50,
) -> dict:
    """
    Estimate dynamic gas fee parameters using Web3.

    Returns a dict with:
      - base_fee           (wei)
      - max_priority_fee   (wei)
      - max_fee_per_gas    (wei)
      - gas_price          (wei)  # legacy fallback
    """
    # 1) Base fee from latest block
    latest = w3.eth.get_block("latest")
    base_fee = latest.get("baseFeePerGas", 0)

    # 2) Node‐suggested tip (method or attr)
    raw = getattr(w3.eth, "max_priority_fee", None)
    if callable(raw):
        priority_fee = raw()
    elif isinstance(raw, int):
        priority_fee = raw
    else:
        priority_fee = w3.to_wei(default_priority_gwei, "gwei")

    # 3) Historical percentile tip
    hist = w3.eth.fee_history(history_blocks, "latest", [reward_pct])
    hist_tip = int(hist["reward"][-1][0])
    priority_fee = max(priority_fee, hist_tip)

    # 4) Buffer to cover up to +12.5% baseFee increase
    buffer = int(base_fee * 0.125)

    max_fee_per_gas = max(base_fee + priority_fee + buffer, base_fee + priority_fee)

    return {
        "base_fee": base_fee,
        "max_priority_fee": priority_fee,
        "max_fee_per_gas": max_fee_per_gas,
        "gas_price": w3.eth.gas_price
    }

def send_usdc(recipient, amount):
    decimals = usdc_contract.functions.decimals().call()
    amt = int(amount * (10 ** decimals))
    nonce = w3.eth.get_transaction_count(evm_account.address)

    tx = usdc_contract.functions.transfer(recipient, amt).build_transaction({
        'chainId': w3.eth.chain_id,
        'nonce': nonce,
    })

    fees = get_dynamic_gas_fees(w3)

    # Dynamically estimate gas
    try:
        gas_limit = w3.eth.estimate_gas(tx)
    except Exception as e:
        gas_limit = 21000  # Fallback gas limit

    # Add EIP-1559 fields
    tx.update({
        'gas': int(gas_limit*1.15),
        'maxFeePerGas': fees['max_fee_per_gas'],
        'maxPriorityFeePerGas': fees['max_priority_fee'],
        'type': 2,
    })

    signed_tx = w3.eth.account.sign_transaction(tx, private_key=EVM_PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    return tx_hash.hex()

app = FastAPI()
templates = Jinja2Templates(directory="templates")

@app.get("/")
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.get("/anchor-toml")
async def get_anchor_toml():
    anchor_toml = requests.get("http://localhost:8080/.well-known/stellar.toml").text
    docs = toml.loads(anchor_toml)
    print(json.dumps(docs, indent=2))
    # Return the relevant parts of the TOML
    print(docs.get("DOCUMENTATION", {}))
    return {"anchor_toml": docs.get("DOCUMENTATION", {})}

# @app.get("/auth")
# def get_challenge(account: str):
#     resp = requests.get(f"{ANCHOR_URL}/auth", params={"account": account})
#     return resp.json()

# @app.post("/auth/complete")
# async def complete_auth(req: Request):
#     data = await req.json()
#     resp = requests.post(f"{ANCHOR_URL}/auth", json=data)
#     return resp.json()

@app.get("/wallet-metrics")
async def wallet_metrics():
    return {
        "address": EVM_ADDRESS,
        "network": "base-sepolia",
        "endpoint": "https://api.example.com/payments",
    }

@app.get("/balance")
async def get_balance():
    data = []

    # Ethereum balance
    try:
        decimals = usdc_contract.functions.decimals().call()
        balance = usdc_contract.functions.balanceOf(evm_account.address).call()
        balance = balance / (10 ** decimals)
        data.append({
            "network": "base-sepolia",
            "address": EVM_ADDRESS,
            "balance": balance
        })
    except Exception as e:
        data.append({
            "network": "base-sepolia",
            "error": str(e)
        })

    # Stellar balance
    try:
        balance = get_stellar_usdc_balance(kp.public_key)
        data.append({
            "network": "stellar-testnet",
            "address": kp.public_key,
            "balance": balance
        })
    except Exception as e:
        data.append({
            "network": "stellar-testnet",
            "error": str(e)
        })

    return {"accounts": data}

@app.get("/bridge")
async def bridge(request: Request, amount: float):
    request_data = {
        "apikey": "",
        "stellar_address": STELLAR_ADDRESS, # Example Ethereum address
        "evm_address": EVM_ADDRESS,  # Example Stellar address
        "target_chain": "stellar-testnet", 
        "amount": amount
    }

    balance = get_evm_usdc_balance(EVM_ADDRESS)
    if balance < amount:
        return {"error": f"Insufficient EVM balance. Current balance: {balance}, required: {amount}"}

    r = requests.post("http://localhost:9000/bridge/request", json=request_data)
    r.raise_for_status()
    print("Bridge request sent successfully:", r.json())
    data = r.json()

    status = data.get("status")

    if status != "watching for source transfer":
        return {"error": f"Unexpected status: {status}"}

    request_id = data.get("request_id")
    bridge_address = data.get("bridge_address")
    amount = data.get("amount", amount)

    base_tx = send_usdc(bridge_address, amount)

    for _ in range(10):
        try:
            r = requests.get(f"http://localhost:9000/bridge/status/{request_id}")
            r.raise_for_status()
            status = r.json().get("status")
            if status == "completed":
                message = r.json()
                return {"status": status, "message": message, "bridge_tx": "0x" + base_tx, "bridge_tx_url": f"{base_base_url}{"0x" + base_tx}", "bridge_address": bridge_address}
        except requests.RequestException as e:
            print(f"Error checking status: {e}")
        time.sleep(5)
    return {"error": "Bridge request timed out or failed to complete."}

@app.get("/withdraw")
async def withdrawal_ui(request: Request, amount: float):

    balance = get_stellar_usdc_balance(kp.public_key)
    if balance < amount:
        return {"error": f"Insufficient Stellar balance. Current balance: {balance}, required: {amount}"}

    anchor_domain = "localhost:8080"  # Replace with your anchor's domain
    toml_data = toml.loads(requests.get(f"http://{anchor_domain}/.well-known/stellar.toml").text)

    print(json.dumps(toml_data, indent=2))
    amount = int(amount)

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
    print(f"Transaction data: {tx_data}")
        
    memo = tx_data.get("memo")
    memo_type = tx_data.get("memo_type")
    destination = tx_data.get("destination_account")
    status = tx_data.get("status")

    if memo and destination:
        print(f"Got payment info! Destination: {destination}, Memo: {memo} ({memo_type})")
        
    else:
        return {
            "error": "Error processing withdrawal request",
            "details": tx_data.get("error_message", "Unknown error")
        }

    # breakpoint()

    stellar_tx = send_stellar_payment(recipient=destination, amount=amount, memo=memo)
    print(f"Stellar transaction sent: {stellar_tx}")
    payload = {
        "jsonrpc": "2.0",
        "id": "1",
        "method": "notify_onchain_funds_received",
        "params": {
            "transaction_id": transaction_id
        }
    }

    for _ in range(10):
        try:
            r = requests.post(f"http://localhost:3000/callbacks/transactions", json=payload)
            r.raise_for_status()
            print(f"Callback response: {r.json()}")
            status = r.json().get("result", {}).get("status")
            if status == "funds_received":
                print("Withdrawal request completed successfully.")
                break
        except requests.RequestException as e:
            print(f"Error checking transaction status: {e}")
        time.sleep(5)

    final_resp = {
        "message": "Withdrawal request processed successfully",
        "withdraw_tx": stellar_tx,
        "withdraw_tx_url": f"{stellar_base_url}{stellar_tx}",
        "transaction_id": transaction_id,
        "destination": destination,
        "memo": memo,
        "status": status,
        "amount": amount
    }

    return final_resp

