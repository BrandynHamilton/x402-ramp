#![cfg(test)]

use super::*;
use soroban_sdk::{Env, Address, BytesN, String, Symbol};
use soroban_sdk::testutils::{Address as _, BytesN as BytesNTestUtils};

fn setup() -> (Env, Address, Address, Address, Address, BytesN<32>) {
    let env = Env::default();

    // Enable mock auth
    env.mock_all_auths();

    // Generate test addresses
    let admin = Address::generate(&env);
    let user = Address::generate(&env);
    let claimer = Address::generate(&env);
    let token = Address::generate(&env);

    // Initialize contract
    EVMBridge::init(env.clone(), admin.clone());

    // Lock funds
    let amount: i128 = 1000;
    let target_chain: i128 = 1;
    let target_address = BytesN::<32>::random(&env);

    let escrow_id = EVMBridge::lock(
        env.clone(),
        token.clone(),
        user.clone(),
        amount,
        target_chain,
        target_address.clone(),
    );

    (env, admin, user, claimer, token, escrow_id)
}

#[test]
fn test_full_escrow_flow() {
    let (env, admin, user, claimer, token, escrow_id) = setup();

    // Escrow should be pending
    let escrow = EVMBridge::get_escrow(env.clone(), escrow_id.clone());
    assert_eq!(escrow.user, user);
    assert_eq!(escrow.amount, 1000);
    assert_eq!(escrow.status, Symbol::new(&env, "pending"));

    // Admin processes escrow
    // No set_invoker needed: mock_all_auths bypasses it
    EVMBridge::process_escrow(env.clone(), escrow_id.clone(), String::from_str(&env, "node1"));
    let escrow = EVMBridge::get_escrow(env.clone(), escrow_id.clone());
    assert_eq!(escrow.status, Symbol::new(&env, "processing"));
    assert_eq!(escrow.node, String::from_str(&env, "node1"));

    // Admin claims escrow for claimer
    let evm_tx = String::from_str(&env, "evm_tx_hash");
    EVMBridge::claim(env.clone(), escrow_id.clone(), token.clone(), evm_tx.clone(), claimer.clone());
    let escrow = EVMBridge::get_escrow(env.clone(), escrow_id.clone());
    assert_eq!(escrow.status, Symbol::new(&env, "claimed"));
    assert_eq!(escrow.evm_tx, evm_tx);

    // Try refund after claim (should panic)
    let result =  EVMBridge::refund(env.clone(), escrow_id.clone(), token.clone(), user.clone());
}

#[test]
fn test_refund_pending() {
    let (env, _admin, user, _claimer, token, escrow_id) = setup();

    // Refund while escrow is still pending
    EVMBridge::refund(env.clone(), escrow_id.clone(), token.clone(), user.clone());
    let escrow = EVMBridge::get_escrow(env.clone(), escrow_id.clone());
    assert_eq!(escrow.status, Symbol::new(&env, "refunded"));
}

#[test]
#[should_panic]
fn test_refund_wrong_user() {
    let (env, _admin, _user, claimer, token, escrow_id) = setup();

    // Unauthorized user attempts refund
    EVMBridge::refund(env.clone(), escrow_id.clone(), token.clone(), claimer.clone());
}
