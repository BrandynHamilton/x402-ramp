// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IERC20 {
    function transferFrom(address, address, uint) external returns (bool);
    function transfer(address, uint) external returns (bool);
}

contract StellarBridge {
    address public admin;
    IERC20 public usdc;

    enum EscrowStatus {
        Pending,
        Processing,
        Claimed,
        Refunded
    }

    struct Escrow {
        address user;
        uint256 amount;
        EscrowStatus status;
        string targetAddress;
        string stellarTx;
        string node; // Optional node for processing
    }

    mapping(bytes32 => Escrow) public escrows;
    mapping(address => uint256) public userNonces;

    event EscrowOpened(
        bytes32 indexed escrowId,
        address indexed user,
        uint256 amount,
        string targetAddress
    );
    event EscrowClaimed(bytes32 indexed escrowId, address indexed claimer);
    event EscrowProcessing(bytes32 indexed escrowId);
    event EscrowRefunded(bytes32 indexed escrowId, address indexed user);

    constructor(address _usdc) {
        admin = msg.sender;
        usdc = IERC20(_usdc);
    }

    modifier onlyAdmin() {
        require(msg.sender == admin, "Only admin can call");
        _;
    }

    function lockFunds(
        address user,
        uint256 amount,
        string calldata targetAddress
    ) external {
        require(amount > 0, "Amount required");

        uint256 nonce = userNonces[user];
        bytes32 escrowId = keccak256(
            abi.encodePacked(user, nonce, amount, targetAddress)
        );
        require(escrows[escrowId].amount == 0, "Escrow already exists");
        require(bytes(targetAddress).length > 0, "Target address required");
        escrows[escrowId] = Escrow(
            user,
            amount,
            EscrowStatus.Pending,
            targetAddress,
            "",
            ""
        );

        userNonces[user]++;

        require(
            usdc.transferFrom(msg.sender, address(this), amount),
            "Transfer failed"
        );

        emit EscrowOpened(escrowId, user, amount, targetAddress);
    }

    function claimFunds(
        bytes32 escrowId,
        address claimer,
        string calldata stellarTx
    ) external onlyAdmin {
        Escrow storage esc = escrows[escrowId];
        require(msg.sender == admin, "Only admin can claim");
        require(esc.status == EscrowStatus.Pending, "Already claimed");

        esc.status = EscrowStatus.Claimed;
        esc.stellarTx = stellarTx;
        require(
            usdc.transfer(claimer, esc.amount),
            "Transfer to bridge wallet failed"
        );

        emit EscrowClaimed(escrowId, claimer);
    }

    function getEscrow(bytes32 escrowId) external view returns (Escrow memory) {
        return escrows[escrowId];
    }

    function getEscrowStatus(
        bytes32 escrowId
    ) external view returns (EscrowStatus) {
        Escrow storage esc = escrows[escrowId];
        require(esc.user != address(0), "Escrow not found");
        return esc.status;
    }

    function refundEscrow(bytes32 escrowId) external {
        Escrow storage esc = escrows[escrowId];
        require(msg.sender == esc.user, "Only user can refund");
        require(esc.status == EscrowStatus.Pending, "Not Pending");

        esc.status = EscrowStatus.Refunded;
        require(usdc.transfer(esc.user, esc.amount), "Refund transfer failed");

        emit EscrowRefunded(escrowId, esc.user);
    }

    function processEscrow(
        bytes32 escrowId,
        string calldata node
    ) external onlyAdmin {
        Escrow storage esc = escrows[escrowId];
        require(msg.sender == admin, "Only admin can process");
        require(esc.status == EscrowStatus.Pending, "Not Pending");

        esc.status = EscrowStatus.Processing;
        esc.node = node; // Store the node for processing

        emit EscrowProcessing(escrowId);
    }
}
