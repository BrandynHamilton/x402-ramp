from stellar_sdk import Keypair, Server, TransactionBuilder, Network, Asset    
import os
from dotenv import load_dotenv
load_dotenv()

STELLAR_PRIVATE_KEY = os.getenv("THIRD_PARTY_STELLAR_KEY")

STELLAR_TESTNET_USD_ISSUER = os.getenv("STELLAR_TESTNET_USD_ISSUER", "GBBD47IF6LWK7P7MDEVSCWR7DPUWV3NY3DTQEVFL4NAT4AQH3ZLLFLA5")
usdc_asset_code = "USDC"
usdc_asset = Asset(usdc_asset_code, STELLAR_TESTNET_USD_ISSUER)  # Circle testnet issuer

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

stellar_tx = send_stellar_payment("GDHH5ISNXNLNMVW62GO45JAFRB2TATB5GINMVZ43TAAVC3BV3GYOTCJ6", 1, "123456")