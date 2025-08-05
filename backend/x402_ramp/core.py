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

