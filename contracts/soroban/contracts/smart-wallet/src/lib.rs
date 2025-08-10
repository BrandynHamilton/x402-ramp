#![no_std]
use soroban_sdk::{contract, contractimpl, contracttype, vec, Env, String, Vec, token, panic_with_error, Address, contracterror};

#[contracterror]
#[derive(Copy, Clone, Debug, Eq, PartialEq, PartialOrd, Ord)]
#[repr(u32)]
pub enum Error {
    InvalidToken = 1,
    InsufficientBalance = 2,
    InvalidAmount = 3,
    Unauthorized = 4,
}

#[contract]
pub struct SmartWallet;

#[contracttype]
enum DataKey {
    Owner,
    Locked,
}

#[contractimpl]
impl SmartWallet {

    fn is_locked(env: &Env) -> bool {
        env.storage().instance().get(&DataKey::Locked).unwrap_or(Ok::<bool, Error>(false)).unwrap()
    }

    fn set_lock(env: &Env, locked: bool) {
        env.storage().instance().set(&DataKey::Locked, &locked);
    }

    pub fn initialize(env: Env, owner: Address) {

        // Prevent re-initialization
        if env.storage().instance().has(&DataKey::Owner) {
            panic!("Already initialized");
        }

        // Store the owner's address
        env.storage().instance().set(&DataKey::Owner, &owner);
    }

    pub fn balance(env: Env, token: Address) -> i128 {
        let client = token::Client::new(&env, &token);
        let this_address = env.current_contract_address();
        client.balance(&this_address)
    }

    pub fn withdraw(env: Env, user: Address, to: Address, token: Address, amount: i128) -> Vec<String> {

        // Check if the caller is the owner
        let owner: Address = env.storage().instance().get::<_, Address>(&DataKey::Owner).unwrap();
        owner.require_auth(); // Authenticates the caller must be the owner

        if Self::is_locked(&env) {
            panic!("Re-entrancy detected");
        }
        Self::set_lock(&env, true); // Lock function

        // Check if the amount is positive
        if amount <= 0 {
            Self::set_lock(&env, false);
            panic_with_error!(&env, Error::InvalidAmount);
        }

        // Check if the contract has sufficient balance
        let client = token::Client::new(&env, &token);
        let this_address = env.current_contract_address();
        let balance = client.balance(&this_address);

        if balance < amount {
            Self::set_lock(&env, false);
            panic_with_error!(&env, Error::InsufficientBalance);
        }

        // Transfer the requested amount to designated "to" address

        client.transfer(&this_address, &to, &amount);

        Self::set_lock(&env, false);

        let mut events = vec![&env, String::from_str(&env, "withdrawal_success")];
        env.events().publish(("withdraw",), to);
        events
    }
}

mod test;
