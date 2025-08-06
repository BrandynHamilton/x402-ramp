import requests
import toml

anchor_domain = "testanchor.stellar.org"  # Replace with your anchor's domain
toml_data = toml.loads(requests.get(f"https://{anchor_domain}/.well-known/stellar.toml").text)

web_auth_endpoint = toml_data["WEB_AUTH_ENDPOINT"]
transfer_server = toml_data["TRANSFER_SERVER_SEP0024"]
signing_key = toml_data["SIGNING_KEY"]

print(f"web_auth_endpoint: {web_auth_endpoint}")
print(f"transfer_server: {transfer_server}")
print(f"signing_key: {signing_key}")