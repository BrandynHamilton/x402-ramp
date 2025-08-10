from stellar_sdk import Keypair, TransactionBuilder, Asset, Server, Network
import requests
import click
import os
from dotenv import load_dotenv
import webbrowser
load_dotenv()

STELLAR_PRIVATE_KEY1 = os.getenv("THIRD_PARTY_STELLAR_KEY") # client
STELLAR_PRIVATE_KEY2 = os.getenv("STELLAR_PRIVATE_KEY") # anchor
STELLAR_PRIVATE_KEY3 = os.getenv("BRIDGE_STELLAR_PRIVATE_KEY") # bridge

private_keys = [STELLAR_PRIVATE_KEY1, STELLAR_PRIVATE_KEY2, STELLAR_PRIVATE_KEY3]

server = Server(horizon_url="https://horizon-testnet.stellar.org")
STELLAR_TESTNET_USD_ISSUER = os.getenv("STELLAR_TESTNET_USD_ISSUER", "GBBD47IF6LWK7P7MDEVSCWR7DPUWV3NY3DTQEVFL4NAT4AQH3ZLLFLA5")
usdc_asset_code = "USDC"
usdc_asset = Asset(usdc_asset_code, STELLAR_TESTNET_USD_ISSUER)  # Circle testnet issuer

def get_stellar_usdc_balance(public_key: str) -> float:
    account = server.accounts().account_id(public_key).call()
    for balance in account["balances"]:
        if balance.get("asset_code") == "USDC" and balance.get("asset_issuer") == STELLAR_TESTNET_USD_ISSUER:
            return float(balance["balance"])
    return 0.0

def send_stellar_payment(recipient, amount, pk, memo=None):
    kp = Keypair.from_secret(pk)
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

@click.group()
def cli():
    pass

@cli.command()
def check_balance():
    for i, key in enumerate(private_keys, start=1):
        kp = Keypair.from_secret(key)
        public_key = kp.public_key
        balance = get_stellar_usdc_balance(public_key)
        print(f"Account {i} ({public_key}) USDC Balance: {balance}")

@click.command()
@click.option('--destination', prompt='Destination Stellar Address', help='The Stellar address to send USDC to.')
@click.option('--amount', prompt='Amount', help='The amount of USDC to send.', type=float)
@click.option('--account', prompt='Account (1 or 2)', help='Which Stellar account to use (1 or 2).', type=int)
def send_usdc(destination, amount, account):
    if account == 1:
        kp = Keypair.from_secret(STELLAR_PRIVATE_KEY1)
    elif account == 2:
        kp = Keypair.from_secret(STELLAR_PRIVATE_KEY2)
    elif account == 3:
        kp = Keypair.from_secret(STELLAR_PRIVATE_KEY3)
    else:
        print("Invalid account selection.")
        return
    print(f"Using Stellar account: {kp.public_key}")
    stellar_account = server.load_account(kp.public_key)
    STELLAR_ADDRESS = kp.public_key
    balance = get_stellar_usdc_balance(STELLAR_ADDRESS)
    if balance < amount:
        print(f"Insufficient balance. Current balance: {balance}, required: {amount}")
        return
    
    print(f"Sending {amount} USDC to {destination} from {STELLAR_ADDRESS}")

    stellar_tx = send_stellar_payment(destination, amount, kp.secret, memo="Payment via x402 Ramp CLI")
    print(f"Transaction successful! Stellar transaction hash: {stellar_tx}")

    base_url = "https://testnet.stellarchain.io/transactions/"
    url = f"{base_url}{stellar_tx}"
    print(f"View transaction on Stellar Explorer: {base_url}{stellar_tx}")
    webbrowser.open(url)

cli.add_command(check_balance)
cli.add_command(send_usdc)

if __name__ == "__main__":
    cli()