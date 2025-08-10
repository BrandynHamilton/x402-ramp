from stellar_sdk import Network, Keypair, Server, Asset
import sys
import os
from dotenv import load_dotenv
load_dotenv()

# sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

print("Current working directory:", os.getcwd())

from bindings.evm_bridge import Client as EVMBridge
from bindings.smart_wallet import Client as SmartWallet

PRIVATE_KEY = os.getenv("STELLAR_PRIVATE_KEY")
EVM_BRIDGE_CONTRACT_ID = os.getenv("EVM_BRIDGE_CONTRACT_ID")
SMART_WALLET_CONTRACT_ID = os.getenv("SMART_WALLET_CONTRACT_ID")

STELLAR_TESTNET_USD_ISSUER = os.getenv("STELLAR_TESTNET_USD_ISSUER", "GBBD47IF6LWK7P7MDEVSCWR7DPUWV3NY3DTQEVFL4NAT4AQH3ZLLFLA5")
usdc_asset_code = "USDC"
usdc_asset = Asset(usdc_asset_code, STELLAR_TESTNET_USD_ISSUER)  # Circle testnet issuer

kp = Keypair.from_secret(PRIVATE_KEY)
print(f'Keypair with public key: {kp.public_key}')
server = Server(horizon_url="https://horizon-testnet.stellar.org")
acc = server.load_account(account_id=kp.public_key)

def sign_tx_func(tx):
    tx.sign(acc)
    return tx

rpc_url = "https://soroban-rpc.testnet.stellar.gateway.fm"

network_passphrase = Network.TESTNET_NETWORK_PASSPHRASE

evm_bridge_client = EVMBridge(EVM_BRIDGE_CONTRACT_ID, rpc_url, network_passphrase)
smart_wallet_client = SmartWallet(SMART_WALLET_CONTRACT_ID, rpc_url, network_passphrase)

try:
    init_tx = evm_bridge_client.init(source=kp.public_key, admin=kp.public_key, signer=kp)
    print("Simulated Transaction:", init_tx.result())
    print("Needs more signatures from:", init_tx.needs_non_invoker_signing_by())
    sim = init_tx.simulate()
    print("Simulation Result:", sim.result())
    # Then submit
    result = init_tx.sign_and_submit()
    print("Transaction Result:", result)
except Exception as e:
    print("Error during initialization:", e)

