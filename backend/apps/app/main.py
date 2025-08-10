from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from flask import request
from pydantic import BaseModel
from web3 import Web3
from stellar_sdk import Account, Server, Asset, Keypair, Network, TransactionBuilder
import os
from dotenv import load_dotenv
import threading
import asyncio
import secrets
from diskcache import Cache

load_dotenv()

app = FastAPI()

cache = Cache("cache")

# Web3 config
infura_key = os.getenv("INFURA_API_KEY")
WEB3_PROVIDER = f"https://base-sepolia.infura.io/v3/{infura_key}"  # or local/testnet
USDC_ADDRESS = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"  # USDC on Base Sepolia
current_dir = os.path.dirname(os.path.abspath(__file__))
print(F'current_dir: {current_dir}')
abi_path = os.path.join(current_dir, "abi", "erc20_abi.json")
print(F'abi_path: {abi_path}')
EVM_PRIVATE_KEY = os.getenv("BRIDGE_EVM_PRIVATE_KEY")

with open(abi_path, "r") as abi_file:
    ERC20_ABI = abi_file.read()

w3 = Web3(Web3.HTTPProvider(WEB3_PROVIDER))
evm_account = w3.eth.account.from_key(EVM_PRIVATE_KEY)
usdc_contract = w3.eth.contract(address=USDC_ADDRESS, abi=ERC20_ABI)
EVM_ADDRESS = evm_account.address
w3.eth.default_account = EVM_ADDRESS

STELLAR_PRIVATE_KEY = os.getenv("BRIDGE_STELLAR_PRIVATE_KEY")

server = Server(horizon_url="https://horizon-testnet.stellar.org")
stellar_kp = Keypair.from_secret(STELLAR_PRIVATE_KEY)
stellar_account = server.load_account(stellar_kp.public_key)
STELLAR_ADDRESS = stellar_kp.public_key
STELLAR_TESTNET_USD_ISSUER = os.getenv("STELLAR_TESTNET_USD_ISSUER", "GBBD47IF6LWK7P7MDEVSCWR7DPUWV3NY3DTQEVFL4NAT4AQH3ZLLFLA5")
usdc_asset_code = "USDC"
usdc_asset = Asset(usdc_asset_code, STELLAR_TESTNET_USD_ISSUER)  # Circle testnet issuer

def has_trustline(account, asset_code, issuer):
    for balance in account['balances']:
        if balance.get("asset_type") == "native":
            continue
        if (
            balance.get("asset_code") == asset_code
            and balance.get("asset_issuer") == issuer
        ):
            return True
    return False

def check_for_usdc_transfer(expected_sender, expected_amount):
    current_block = w3.eth.block_number
    logs = usdc_contract.events.Transfer().get_logs(
        from_block=current_block - 20,
        to_block='latest'
    )
    for log in logs:
        if log['args']['from'].lower() == expected_sender.lower() and \
           log['args']['to'].lower() == evm_account.address.lower() and \
           log['args']['value'] >= expected_amount:
            return log['transactionHash'].hex()
    return None

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

def handle_payment(payment):
    print("💸 Payment received!")
    print(f"Type: {payment['type']}")
    print(f"From: {payment['from']}")
    print(f"To: {payment['to']}")
    print(f"Asset: {payment['asset_type']}")
    print(f"Amount: {payment['amount']}")

def listen_for_payments():
    print("🔁 Listening for Stellar payments...")
    for payment in server.payments().for_account(stellar_kp.public_key).cursor("now").stream():
        if payment["type"] == "payment":
            handle_payment(payment)

class BridgeRequest(BaseModel):
    apikey: str  # user api key
    target_chain: str # target chain (e.g., "base", "stellar")
    evm_address: str  # source address (EVM or Stellar)
    stellar_address: str  # target address (EVM or Stellar)
    amount: float  # amount to bridge

def send_usdc_from_bridge_wallet(recipient, amount):
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

def is_valid_evm_address(address: str) -> bool:
    return Web3.is_address(address)

def is_valid_stellar_address(address: str) -> bool:
    return address.startswith("G") and len(address) == 56

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

async def monitor_transfer_and_bridge(req: BridgeRequest, request_id: str):
    print(f"Background task started for request: {req}")
    if req.target_chain == "stellar-testnet":
        # EVM → Stellar bridge
        print(f"🔁 Watching for USDC from {req.evm_address} on EVM...")

        while True:
            tx = check_for_usdc_transfer(req.evm_address, int(req.amount * (10**6)))  # USDC = 6 decimals
            if tx:
                print(f"✅ EVM Transfer detected: {tx}")
                stellar_tx = send_stellar_payment(req.stellar_address, req.amount, memo=f"Bridge from {req.evm_address[0:5]}")
                info = dict(cache[request_id])  # get a mutable copy
                info.update({"status": "completed", "target_tx": stellar_tx})
                cache[request_id] = info
                print(f"✅ Sent to Stellar: {stellar_tx}")
                break
            await asyncio.sleep(5)

    elif req.target_chain == "base-sepolia":
        # Stellar → EVM bridge
        print(f"🔁 Watching for USDC from {req.stellar_address} on Stellar...")

        seen = set()
        for payment in server.payments().for_account(stellar_kp.public_key).cursor("now").stream():
            if payment["type"] == "payment" and \
               payment["from"] == req.stellar_address and \
               payment["to"] == stellar_kp.public_key and \
               float(payment["amount"]) >= req.amount and \
               payment["id"] not in seen:

                seen.add(payment["id"])
                print(f"✅ Stellar Payment detected: {payment}")
                # For MVP, send from EVM bridge wallet to user
                evm_tx = send_usdc_from_bridge_wallet(req.evm_address, req.amount)
                info = dict(cache[request_id])  # get a mutable copy
                info.update({"status": "completed", "target_tx": evm_tx})
                cache[request_id] = info        # write back to cache
                print(f"✅ Sent to Base: {evm_tx}")
                break

# cache = {}

@app.get("/")
async def root():
    return {"message": "Welcome to the Base Sepolia <-> Stellar Testnet Bridge API"}

@app.get("/health")
async def health_check():
    data = {}
    if w3.isConnected():
        data[w3.eth.chain_id] = {"status": "ok",
                                 "address": evm_account.address,
                                 "block_number": w3.eth.block_number
            }
    else:
        data[w3.eth.chain_id] = {"status": "error", "message": "Web3 provider not reachable"}

    try:
        stellar_account = server.load_account(stellar_kp.public_key)
        data["stellar"] = {
            "status": "ok",
            "address": stellar_kp.public_key,
            "sequence": stellar_account.sequence
        }
    except Exception as e:
        data["stellar"] = {
            "status": "error",
            "message": str(e)
        }
    return data

@app.get("/bridge/supported_chains")
async def supported_chains():
    return {"chains": ["stellar-testnet", "base-sepolia"]}

@app.get("/bridge/status/{request_id}")
async def request_status(request_id: str):
    req_info = cache.get(request_id)
    if req_info is None:
        return {"error": "Request not found"}
    # Make a copy of the request dict and remove apikey if present
    info = dict(req_info)  # shallow copy
    print(f'info: {info}')
    if "request" in info and isinstance(info["request"], BridgeRequest):
        info["request"] = dict(info["request"])  # copy request dict
        info["request"].pop("apikey", None)
        print(f'info: {info}')
    status = info.get("status")
    info.pop("status", None)
    return {"status": status, "info": info}

@app.get("/bridge/balance")
async def get_balance():
    data = {}
    try:
        decimals = usdc_contract.functions.decimals().call()
        balance = usdc_contract.functions.balanceOf(evm_account.address).call()
        balance = balance / (10 ** decimals)  # Convert to human-readable format
        data["ethereum"] = balance
    except Exception as e:
        data["ethereum_error"] = str(e)

    try:
        balance = get_stellar_usdc_balance(stellar_kp.public_key)
        data["stellar"] = balance
    except Exception as e:
        data["stellar_error"] = str(e)

    return data

@app.post("/bridge/request")
async def request_bridge(req: BridgeRequest, background_tasks: BackgroundTasks):
    # Validate chain target
    if req.target_chain not in ["stellar-testnet", "base-sepolia"]:
        raise HTTPException(status_code=400, detail="Invalid target_chain")        

    salt = os.urandom(32).hex()
    if not salt.startswith("0x"):
        salt = "0x" + salt
    settlement_id = secrets.token_hex(16)
    id_hash_bytes = w3.solidity_keccak(["bytes32", "string"], [salt, settlement_id])
    request_id = id_hash_bytes.hex()
    status = "pending"

    source_chain = "stellar-testnet" if req.target_chain == "base-sepolia" else "base-sepolia"

    # Validate address format
    if req.target_chain == "stellar-testnet":
        bridge_address = EVM_ADDRESS
        if not is_valid_stellar_address(req.stellar_address) or not is_valid_evm_address(req.evm_address):
            raise HTTPException(status_code=400, detail="Invalid source/target address format for EVM → Stellar")
        
        # Check if recipient has trustline to USDC
        recipient_account = server.accounts().account_id(req.stellar_address).call()
        if not has_trustline(recipient_account, usdc_asset_code, STELLAR_TESTNET_USD_ISSUER):
            raise HTTPException(status_code=400, detail="Recipient does not have a trustline to USDC")
        
        # Check Stellar balance of bridge wallet
        bridge_balance = get_stellar_usdc_balance(stellar_kp.public_key)
        if bridge_balance < req.amount:
            raise HTTPException(status_code=400, detail=f"Bridge wallet has insufficient balance on Stellar: {bridge_balance} USDC")

    elif req.target_chain == "base-sepolia":
        bridge_address = STELLAR_ADDRESS
        if not is_valid_stellar_address(req.stellar_address) or not is_valid_evm_address(req.evm_address):
            raise HTTPException(status_code=400, detail="Invalid source/target address format for Stellar → EVM")
        
        # Check Base (EVM) balance of bridge wallet
        bridge_balance = get_evm_usdc_balance(evm_account.address)
        if bridge_balance < req.amount:
            raise HTTPException(status_code=400, detail=f"Bridge wallet has insufficient balance on Base: {bridge_balance} USDC")

    cache[request_id] = {
        "request": req,  # Remove apikey from request
        "status": status
    }

    # Launch background task to monitor and bridge
    background_tasks.add_task(monitor_transfer_and_bridge, req, request_id)
    return {"status": "watching for source transfer",
            "request_id": request_id,
            "message": f"Request {request_id} is being processed. Please send USDC on {source_chain} to the bridge address {bridge_address}.",
            "source_chain": source_chain,
            "source_chain_id": w3.eth.chain_id if source_chain == "base-sepolia" else "n/a",
            "bridge_address": bridge_address,
        }
