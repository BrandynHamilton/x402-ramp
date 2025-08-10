#![cfg(test)]

use super::*;
use soroban_sdk::{testutils::{Address as _, Ledger, LedgerInfo, MockAuth}, Env, BytesN, Bytes, Address};
use soroban_sdk::token::TokenClient;
use soroban_token_sdk::metadata::TokenMetadata;

fn create_token_contract(env: &Env, admin: &Address) -> TokenClient {
    let wasm = env.deployer().upload_contract_wasm(soroban_token_sdk::TOKEN_WASM); // Load the embedded token Wasm
    let id = env.deployer().upload_contract_wasm(wasm);
    let salt = BytesN::<32>::from_array(&env, &[0; 32]);
    let client = TokenClient::new(env, &env.deployer().with_current_contract(salt).deploy(wasm));
    client.initialize(admin, &TokenMetadata {
        name: "TestToken".into(),
        symbol: "TST".into(),
        decimals: 7,
    });
    client
}

#[test]
fn test_withdraw() {
    let env = Env::default();
    env.mock_all_auths();

    // Setup ledger info (e.g., current timestamp)
    env.ledger().set(LedgerInfo {
        timestamp: 0,
        protocol_version: 20,
        sequence_number: 1,
        network_id: [0; 32],
        base_reserve: 5,
        min_temp_entry_ttl: 1,
        min_persistent_entry_ttl: 1,
        max_entry_ttl: 10000,
    });

    // Register mock token contract

    // Register smart contract
    let contract_id = env.register(SmartWallet, ());
    let client = SmartWalletClient::new(&env, &contract_id);

    // Random addresses
    let user_bytes = BytesN::<32>::from_array(&env, &[1; 32]);
    let recipient_bytes = BytesN::<32>::from_array(&env, &[2; 32]);

    let owner = Address::from_string_bytes(&user_bytes);
    let recipient = Address::from_string_bytes(&recipient_bytes);

    // Initialize smart wallet
    client.initialize(&owner);

    let token_client = create_token_contract(&env, &owner);
    token_client.mint(&owner, &1000);
    let token_id = token_client.id();

    // Confirm contract balance
    let initial_balance = client.balance(&token_id);
    assert_eq!(initial_balance, 1000);

    // Withdraw 300 tokens to recipient
    client.withdraw(&owner, &recipient, &token_id, &300);

    // Check remaining balance in contract
    let final_balance = client.balance(&token_id);
    assert_eq!(final_balance, 700);

    // Confirm recipient got the funds
    let recipient_balance = token_client.balance(&recipient);
    assert_eq!(recipient_balance, 300);
}
