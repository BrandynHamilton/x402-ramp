from stellar_sdk import Server, Keypair, TransactionBuilder, Network, Asset
import os
from dotenv import load_dotenv
import requests
load_dotenv()

STELLAR_PRIVATE_KEY = os.getenv("STELLAR_PRIVATE_KEY")
kp = Keypair.from_secret(STELLAR_PRIVATE_KEY)
print(f"Account: {kp.public_key}")
BRIDGE_STELLAR_PRIVATE_KEY = os.getenv("BRIDGE_STELLAR_PRIVATE_KEY")
STELLAR_TESTNET_USD_ISSUER = os.getenv("STELLAR_TESTNET_USD_ISSUER", "GBBD47IF6LWK7P7MDEVSCWR7DPUWV3NY3DTQEVFL4NAT4AQH3ZLLFLA5")
THIRD_PARTY_STELLAR_KEY = os.getenv("THIRD_PARTY_STELLAR_KEY")
usdc_asset_code = "USDC"

server = Server(horizon_url="https://horizon-testnet.stellar.org")

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

for key in [BRIDGE_STELLAR_PRIVATE_KEY, STELLAR_PRIVATE_KEY, THIRD_PARTY_STELLAR_KEY, "SBYAT7FNQ54ZA46AMCM4FQK5FHIYMFQ33PN4ADXOVTEUE3ECXCPPLO7O"]:
    source_kp = Keypair.from_secret(key)  # Your Stellar private key
    # source_account = server.load_account(account_id=source_kp.public_key)
    try:
        source_account = server.accounts().account_id(source_kp.public_key).call()
    except Exception as e:
        url = "https://friendbot.stellar.org"
        response = requests.get(url, params={"addr": source_kp.public_key})
        if response.status_code == 200:
            print(f"SUCCESS! You have a new account :)\n{response.text}")
            source_account = server.accounts().account_id(source_kp.public_key).call()

    if has_trustline(source_account, usdc_asset_code, STELLAR_TESTNET_USD_ISSUER):
        print(f"✅ Trustline exists {source_kp.public_key}.")
        for balance in source_account['balances']:
            # print(f'balance: {balance.keys()}')
            print(f"Type: {balance.get('asset_code', 'native')}, Balance: {balance['balance']}")
    else:
        print(f"❌ No trustline found {source_kp.public_key}.")

        source_account = server.load_account(source_kp.public_key)
        txn = (
            TransactionBuilder(
                source_account=source_account,
                network_passphrase=Network.TESTNET_NETWORK_PASSPHRASE,
                base_fee=100
            )
            .append_change_trust_op(asset=usdc_asset)
            .set_timeout(30)
            .build()
        )

        txn.sign(source_kp)
        resp = server.submit_transaction(txn)
        print(resp)

        account = server.accounts().account_id(source_kp.public_key).call()
        for balance in account['balances']:
            print(f"Type: {balance.get('asset_code', 'native')}, Balance: {balance['balance']}")

        trustline_bool = has_trustline(source_account, usdc_asset_code, STELLAR_TESTNET_USD_ISSUER)

        print("Trustline status after transaction:")
        print("✅ Trustline exists." if trustline_bool else "❌ No trustline found.")