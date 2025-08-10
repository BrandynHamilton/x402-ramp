# x402 Ramp

x402 Ramp is a programmable USDC to fiat off-ramp UI designed primarily for Latin American banking systems. It leverages the x402 payments protocol and integrates with Stellar anchors to provide seamless bridging and withdrawing of funds.

## Overview

This project provides a user interface for:

- Checking account balances
- Bridging USDC tokens across chains
- Withdrawing fiat currency via supported banking rails
- Managing KYC information (stored or new)

The UI supports multiple currencies and countries, and includes programmatic flows for automated payments.

An Anchor Platform and testnet EVM <-> Stellar USDC bridge were also deployed.

## Requirements

- Python 3.10+
- Docker (optional for containerized deployment)
- `uv` or `pip` + `venv` for Python dependency management

## Setup

### Run the Anchor Platform

```bash
cd anchor
docker compose up
```

### Run the Bridge

```bash
cd backend
docker compose up
```

### Run the Dashboard

```bash
cd backend
uv venv   # or python -m venv .venv
uv sync

.venv\scripts\activate

uvicorn app:app --reload --port 9002

```

> Ensure `.env` contains INFURA_API_KEY, THIRD_PARTY_EVM_KEY, THIRD_PARTY_STELLAR_KEY

The backend exposes the following endpoints:

/balance — Fetch user balances

/bridge — Initiate bridge transactions

/withdraw — Initiate withdrawal transactions

/anchor-toml — Fetch Stellar anchor metadata

/wallet-metrics — Retrieve wallet metrics data

## How to Use

1. Open the UI in a browser.

2. Use the language toggle to switch between English and Spanish.

3. Check balances via the form.

4. Use the Bridge / Withdraw form to initiate transactions.

5. Enter or update KYC information as needed.
