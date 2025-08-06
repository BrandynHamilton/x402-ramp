from stellar_sdk import Keypair, TransactionEnvelope, Network
import json
import requests
import toml
import os
from dotenv import load_dotenv
load_dotenv()

STELLAR_PRIVATE_KEY = os.getenv("STELLAR_PRIVATE_KEY")  # Replace with your Stellar secret key

kp = Keypair.from_secret(STELLAR_PRIVATE_KEY)

anchor_domain = "testanchor.stellar.org"  # Replace with your anchor's domain
toml_data = toml.loads(requests.get(f"https://{anchor_domain}/.well-known/stellar.toml").text)

web_auth_endpoint = toml_data["WEB_AUTH_ENDPOINT"]
transfer_server = toml_data["TRANSFER_SERVER_SEP0024"]
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
