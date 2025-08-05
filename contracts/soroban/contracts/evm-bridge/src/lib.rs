#![no_std]

use soroban_sdk::{
    contract, contractimpl, contracttype, contracterror, Symbol, Address, Env, BytesN, Bytes, String, token, panic_with_error,
};

use soroban_sdk::xdr::ToXdr;

#[derive(Clone, Debug, Eq, PartialEq, PartialOrd, Ord)]
#[contracttype]
pub enum DataKey {
    Admin,
    EscrowNonce(Address),
}

const ADMIN_KEY: &str = "admin";

#[derive(Clone)]
#[contracttype]
pub struct Escrow {
    pub user: Address,
    pub amount: i128,
    pub status: Symbol,
    pub target_address: BytesN<32>,
    pub evm_tx: String,
    pub node: String,
}

#[contracterror]
#[derive(Debug, Eq, PartialEq)]
pub enum Error {
    AlreadyInitialized = 1,
    AdminNotInitialized = 2,
    EscrowNotFound = 3,
    EscrowNotPending = 4,
    EscrowNotProcessing = 5,
    UnauthorizedRefund = 6,
    InvalidAddressLength = 7,
    InvalidAmount = 8,
}

#[contract]
pub struct EVMBridge;

#[contractimpl]
impl EVMBridge {
    pub fn init(env: Env, admin: Address) {
        if env.storage().instance().has(&DataKey::Admin) {
            panic_with_error!(&env, Error::AlreadyInitialized);
        }
        admin.require_auth();
        env.storage().instance().set(&DataKey::Admin, &admin);
    }

    pub fn get_admin(env: &Env) -> Address {
        env.storage().instance()
            .get::<_, Address>(&DataKey::Admin)
            .unwrap_or_else(|| panic_with_error!(env, Error::AdminNotInitialized))
    }

    pub fn get_user_nonce(env: Env, user: Address) -> u32 {
        let storage = env.storage().instance();
        let key = (DataKey::EscrowNonce(user.clone()), user);
        storage.get::<_, u32>(&key).unwrap_or(0)
    }

    pub fn lock(
        env: Env,
        token: Address,
        user: Address,
        amount: i128,
        target_chain: i128,
        target_address: BytesN<32>,
    ) -> BytesN<32> {
        if target_address.len() != 32 {
            panic_with_error!(&env, Error::InvalidAddressLength);
        }
        if amount <= 0 {
            panic_with_error!(&env, Error::InvalidAmount);
        }

        // Get & increment user-specific nonce
        let key = (DataKey::EscrowNonce(user.clone()), user.clone());
        let mut nonce: u32 = env.storage().instance().get(&key).unwrap_or(0);
        env.storage().instance().set(&key, &(nonce + 1));

        // Create deterministic ID: sha256(user || nonce)
        // Create an empty Bytes buffer
        let user_xdr_bytes: Bytes = user.clone().to_xdr(&env);

        // Convert nonce to 4 bytes big endian (simple u32 array)
        let nonce_bytes: [u8; 4] = nonce.to_be_bytes();

        // Create a Bytes buffer to combine user_xdr_bytes + nonce_bytes
        let mut combined = Bytes::new(&env);
        combined.append(&user_xdr_bytes);
        combined.append(&Bytes::from_array(&env, &nonce_bytes));

        // Hash combined bytes for ID
        let id = env.crypto().sha256(&combined);

        let escrow = Escrow {
            user: user.clone(),
            amount,
            status: Symbol::new(&env, "pending"),
            target_address: target_address.clone(),
            evm_tx: String::from_str(&env, ""),
            node: String::from_str(&env, ""),
        };
        let storage = env.storage().instance();
        storage.set(&id, &escrow);

        let allowance = token::Client::new(&env, &token).allowance(
            &user,
            &env.current_contract_address(),
        );

        if allowance < amount {
            panic_with_error!(&env, Error::InvalidAmount);
        }

        token::Client::new(&env, &token).transfer_from(
            &env.current_contract_address(), // spender (the contract itself)
            &user,                           // from (the user)
            &env.current_contract_address(), // to (the contract, holding funds)
            &amount,                         // amount
        );

        let id_bytes: [u8; 32] = id.to_array();
        let id_bytesn = BytesN::<32>::from_array(&env, &id_bytes);
        
        env.events().publish(
            ("escrow_opened",),
            (id_bytesn.clone(), user, amount, target_chain, target_address),
        );

        id_bytesn
    }

    pub fn get_escrow(env: Env, id: BytesN<32>) -> Escrow {
        let storage = env.storage().instance();
        storage.get(&id).unwrap_or_else(|| panic_with_error!(&env, Error::EscrowNotFound))
    }

    pub fn get_escrow_status(env: Env, id: BytesN<32>) -> Symbol {
        let storage = env.storage().instance();
        let escrow = storage.get::<_, Escrow>(&id)
            .unwrap_or_else(|| panic_with_error!(&env, Error::EscrowNotFound));
        escrow.status
    }

    pub fn process_escrow(env: Env, id: BytesN<32>, node: String) {
        let admin = Self::get_admin(&env);
        admin.require_auth();

        let mut escrow = {
            let storage = env.storage().instance();
            storage.get::<_, Escrow>(&id)
                .unwrap_or_else(|| panic_with_error!(&env, Error::EscrowNotFound))
        };

        if escrow.status != Symbol::new(&env, "pending") {
            panic_with_error!(&env, Error::EscrowNotPending);
        }

        escrow.status = Symbol::new(&env, "processing");
        escrow.node = node;
        escrow.evm_tx = String::from_str(&env, "");
        let storage = env.storage().instance();
        storage.set(&id, &escrow);
    }

    pub fn claim(env: Env, id: BytesN<32>, token: Address, evm_tx: String, claimer: Address) {
        let admin = Self::get_admin(&env);
        admin.require_auth();

        let mut escrow = {
            let storage = env.storage().instance();
            storage.get::<_, Escrow>(&id)
                .unwrap_or_else(|| panic_with_error!(&env, Error::EscrowNotFound))
        };

        if escrow.status != Symbol::new(&env, "processing") {
            panic_with_error!(&env, Error::EscrowNotProcessing);
        }

        token::Client::new(&env, &token).transfer(
            &env.current_contract_address(),
            &claimer,
            &escrow.amount,
        );

        escrow.status = Symbol::new(&env, "claimed");
        escrow.evm_tx = evm_tx;
        let storage = env.storage().instance();
        storage.set(&id, &escrow);

        env.events().publish(("escrow_claimed",), id);
    }

    pub fn refund(env: Env, id: BytesN<32>, token: Address, user: Address) {
        let mut escrow = {
            let storage = env.storage().instance();
            storage.get::<_, Escrow>(&id)
                .unwrap_or_else(|| panic_with_error!(&env, Error::EscrowNotFound))
        };

        if escrow.status != Symbol::new(&env, "pending") {
            panic_with_error!(&env, Error::EscrowNotPending);
        }
        if escrow.user != user {
            panic_with_error!(&env, Error::UnauthorizedRefund);
        }

        token::Client::new(&env, &token).transfer(
            &env.current_contract_address(),
            &user,
            &escrow.amount,
        );

        escrow.status = Symbol::new(&env, "refunded");
        let storage = env.storage().instance();
        storage.set(&id, &escrow);

        env.events().publish(("escrow_refunded",), id);
    }
}

mod test;