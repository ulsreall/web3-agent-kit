"""Account Abstraction Module — ERC-4337 bundler and paymaster integration.

Supports smart contract wallets, UserOperations, gas sponsorship
via paymasters, and account factory deployment.

Usage::
    from web3_agent_kit.account_abstraction import AAWallet, AAPaymaster
    
    wallet = AAWallet(
        rpc_url="https://base.llamarpc.com",
        entry_point="0x5FF137D4b0FDCD49DcA30c7CF57E578a026d2789",
        factory="0x...",
    )
    wallet.deploy_account(owner="0x...")
    op = wallet.send_user_op(
        to="0x...",
        value=0,
        data="0x...",
    )
    print(f"UserOp hash: {op.user_op_hash}")
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class AAChain(Enum):
    """Supported chains for ERC-4337."""
    ETHEREUM = "ethereum"
    BASE = "base"
    ARBITRUM = "arbitrum"
    OPTIMISM = "optimism"
    POLYGON = "polygon"
    BSC = "bsc"
    AVALANCHE = "avalanche"


# ERC-4337 EntryPoint addresses (canonical v0.6)
ENTRY_POINTS: dict[str, str] = {
    "ethereum": "0x5FF137D4b0FDCD49DcA30c7CF57E578a026d2789",
    "base": "0x5FF137D4b0FDCD49DcA30c7CF57E578a026d2789",
    "arbitrum": "0x5FF137D4b0FDCD49DcA30c7CF57E578a026d2789",
    "optimism": "0x5FF137D4b0FDCD49DcA30c7CF57E578a026d2789",
    "polygon": "0x5FF137D4b0FDCD49DcA30c7CF57E578a026d2789",
}

# Bundler RPCs
BUNDLER_RPCS: dict[str, str] = {
    "ethereum": "https://api.pimlico.io/v1/ethereum/rpc",
    "base": "https://api.pimlico.io/v1/base/rpc",
    "arbitrum": "https://api.pimlico.io/v1/arbitrum/rpc",
    "optimism": "https://api.pimlico.io/v1/optimism/rpc",
    "polygon": "https://api.pimlico.io/v1/polygon/rpc",
}

# Known factory addresses
KNOWN_FACTORIES: dict[str, str] = {
    "simple_account_v7": "0x9406Cc6185a346906296840746125a0E44976454",
    "safe_v143": "0xa6B71E26C5e0845f74c812102Ca7114b6a896AB2",
    "kernel_v3": "0x5de4839a76cf55d0c90e2061ef4386d962E15ae3",
}


@dataclass
class UserOperation:
    """ERC-4337 UserOperation structure."""
    sender: str
    nonce: int
    init_code: str = "0x"
    call_data: str = "0x"
    call_gas_limit: int = 0
    verification_gas_limit: int = 0
    pre_verification_gas: int = 0
    max_fee_per_gas: int = 0
    max_priority_fee_per_gas: int = 0
    paymaster_and_data: str = "0x"
    signature: str = "0x"


@dataclass
class UserOpResult:
    """Result of a UserOperation submission."""
    user_op_hash: str
    tx_hash: Optional[str] = None
    status: str = "pending"  # pending, confirmed, failed
    block_number: Optional[int] = None
    gas_used: int = 0
    actual_gas_cost: int = 0


@dataclass
class AAWalletInfo:
    """Smart account wallet information."""
    address: str
    owner: str
    factory: str
    deployed: bool
    nonce: int = 0
    balance: float = 0.0


class AAPaymaster:
    """Paymaster configuration for gas sponsorship.

    Supports: verifying paymaster (sponsor gas for specific operations),
    token paymaster (pay gas with ERC-20 tokens).

    Example::
        paymaster = AAPaymaster(
            type="verifying",
            url="https://api.pimlico.io/v1/base/rpc",
            policy_id="sponsor_transfers",
        )
    """

    def __init__(
        self,
        paymaster_type: str = "verifying",
        url: Optional[str] = None,
        policy_id: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        self.paymaster_type = paymaster_type
        self.url = url
        self.policy_id = policy_id
        self.api_key = api_key

    def get_paymaster_data(
        self,
        user_op: UserOperation,
        entry_point: str,
        chain_id: int,
    ) -> dict:
        """Get paymaster and data for a UserOperation.

        Returns:
            dict with paymasterAndData and verificationGasLimit
        """
        if self.paymaster_type == "verifying":
            return self._verifying_paymaster(user_op, entry_point, chain_id)
        elif self.paymaster_type == "token":
            return self._token_paymaster(user_op)
        return {"paymasterAndData": "0x", "verificationGasLimit": user_op.verification_gas_limit}

    def _verifying_paymaster(self, user_op: UserOperation, entry_point: str, chain_id: int) -> dict:
        """Get verifying paymaster data via Pimlico API."""
        if not self.url or not self.api_key:
            raise ValueError("Paymaster URL and API key required for verifying paymaster")

        import requests
        payload = {
            "jsonrpc": "2.0",
            "method": "pm_sponsorUserOperation",
            "params": [{
                "sender": user_op.sender,
                "nonce": hex(user_op.nonce),
                "initCode": user_op.init_code,
                "callData": user_op.call_data,
                "callGasLimit": hex(user_op.call_gas_limit),
                "verificationGasLimit": hex(user_op.verification_gas_limit),
                "preVerificationGas": hex(user_op.pre_verification_gas),
                "maxFeePerGas": hex(user_op.max_fee_per_gas),
                "maxPriorityFeePerGas": hex(user_op.max_priority_fee_per_gas),
                "paymasterAndData": "0x",
                "signature": user_op.signature,
            }, entry_point, hex(chain_id)],
            "id": 1,
        }

        if self.policy_id:
            payload["params"][0]["sponsorshipPolicyId"] = self.policy_id

        resp = requests.post(
            self.url,
            json=payload,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=15,
        )
        data = resp.json()
        if "error" in data:
            raise ValueError(f"Paymaster error: {data['error']}")

        result = data.get("result", {})
        return {
            "paymasterAndData": result.get("paymasterAndData", "0x"),
            "verificationGasLimit": int(result.get("verificationGasLimit", "0x0"), 16),
        }

    def _token_paymaster(self, user_op: UserOperation) -> dict:
        """Token paymaster: encode token + exchange rate."""
        # Token paymaster allows paying gas with ERC-20 tokens
        # This is a simplified implementation
        return {
            "paymasterAndData": "0x",
            "verificationGasLimit": user_op.verification_gas_limit,
        }


class AAWallet:
    """ERC-4337 Smart Account Wallet.

    Manages a smart contract wallet with ERC-4337 account abstraction.
    Supports account deployment, UserOperations, and paymaster integration.

    Example::
        wallet = AAWallet(
            rpc_url="https://base.llamarpc.com",
            chain="base",
            factory="simple_account_v7",
        )
        info = wallet.deploy_account(owner="0x...")
        print(f"Account deployed at: {info.address}")
    """

    def __init__(
        self,
        rpc_url: str,
        chain: str = "base",
        factory: str = "simple_account_v7",
        bundler_url: Optional[str] = None,
        paymaster: Optional[AAPaymaster] = None,
        api_key: Optional[str] = None,
    ):
        self.rpc_url = rpc_url
        self.chain = chain
        self.factory_name = factory
        self.factory_address = KNOWN_FACTORIES.get(factory, factory)
        self.bundler_url = bundler_url or BUNDLER_RPCS.get(chain, rpc_url)
        self.paymaster = paymaster
        self.api_key = api_key
        self.entry_point = ENTRY_POINTS.get(chain, ENTRY_POINTS["ethereum"])

        from web3 import Web3
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))

    def get_counterfactual_address(self, owner: str, salt: int = 0) -> str:
        """Compute the counterfactual address of the smart account before deployment."""
        from web3 import Web3

        # Simplified: using create2 address computation
        # In production, this should call the factory's getAddress()
        init_code = self._encode_init_code(owner, salt)
        address = Web3.keccak(
            bytes.fromhex("ff") +
            Web3.to_bytes(hexstr=self.factory_address) +
            Web3.to_bytes(salt).rjust(32, b'\x00') +
            Web3.keccak(hexstr=init_code)
        )[12:].hex()
        return Web3.to_checksum_address("0x" + address)

    def deploy_account(self, owner: str, salt: int = 0) -> AAWalletInfo:
        """Deploy a new smart account.

        Args:
            owner: Owner address
            salt: Create2 salt

        Returns:
            AAWalletInfo with deployed account details
        """
        address = self.get_counterfactual_address(owner, salt)

        # Check if already deployed
        code = self.w3.eth.get_code(address)
        deployed = len(code) > 2

        if not deployed:
            # Deploy via factory — this is a simplified representation
            # In production, send a UserOp with initCode set
            logger.info(f"Account {address} not yet deployed. Use send_user_op with init_code to deploy.")

        return AAWalletInfo(
            address=address,
            owner=owner,
            factory=self.factory_address,
            deployed=deployed,
            nonce=0,
        )

    def send_user_op(
        self,
        to: str,
        value: int = 0,
        data: str = "0x",
        sender: Optional[str] = None,
        owner: Optional[str] = None,
    ) -> UserOpResult:
        """Build and send a UserOperation.

        Args:
            to: Target address
            value: Value in wei
            data: Calldata
            sender: Smart account address (computed if not provided)
            owner: Owner address

        Returns:
            UserOpResult with hash and status
        """
        from web3 import Web3

        if not sender and owner:
            sender = self.get_counterfactual_address(owner)
        if not sender:
            raise ValueError("Either sender or owner must be provided")

        chain_id = self.w3.eth.chain_id
        nonce = 0  # Should fetch from entry point

        # Build UserOperation
        user_op = UserOperation(
            sender=sender,
            nonce=nonce,
            call_data=data,
            call_gas_limit=200000,
            verification_gas_limit=500000,
            pre_verification_gas=50000,
            max_fee_per_gas=self.w3.eth.gas_price,
            max_priority_fee_per_gas=min(self.w3.eth.gas_price, 2_000_000_000),
        )

        # Check if account needs deployment
        code = self.w3.eth.get_code(sender)
        if len(code) <= 2 and owner:
            user_op.init_code = self._encode_init_code(owner, 0)

        # Apply paymaster
        if self.paymaster:
            pm_data = self.paymaster.get_paymaster_data(user_op, self.entry_point, chain_id)
            user_op.paymaster_and_data = pm_data["paymasterAndData"]
            user_op.verification_gas_limit = pm_data.get("verificationGasLimit", user_op.verification_gas_limit)

        # Submit to bundler
        uo_hash = self._submit_to_bundler(user_op)

        return UserOpResult(
            user_op_hash=uo_hash,
            status="pending",
        )

    def _submit_to_bundler(self, user_op: UserOperation) -> str:
        """Submit UserOperation to bundler via eth_sendUserOperation."""
        import json
        import requests

        payload = {
            "jsonrpc": "2.0",
            "method": "eth_sendUserOperation",
            "params": [{
                "sender": user_op.sender,
                "nonce": hex(user_op.nonce),
                "initCode": user_op.init_code,
                "callData": user_op.call_data,
                "callGasLimit": hex(user_op.call_gas_limit),
                "verificationGasLimit": hex(user_op.verification_gas_limit),
                "preVerificationGas": hex(user_op.pre_verification_gas),
                "maxFeePerGas": hex(user_op.max_fee_per_gas),
                "maxPriorityFeePerGas": hex(user_op.max_priority_fee_per_gas),
                "paymasterAndData": user_op.paymaster_and_data,
                "signature": user_op.signature,
            }, self.entry_point],
            "id": 1,
        }

        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        resp = requests.post(self.bundler_url, json=payload, headers=headers, timeout=15)
        data = resp.json()

        if "error" in data:
            raise ValueError(f"Bundler error: {data['error']}")

        return data["result"]

    def _encode_init_code(self, owner: str, salt: int) -> str:
        """Encode factory init code for account deployment."""
        from web3 import Web3
        # SimpleAccount factory: createAccount(owner, salt)
        factory_abi = ["function createAccount(address owner,uint256 salt)"]
        contract = self.w3.eth.contract(address=self.factory_address, abi=factory_abi)
        return self.factory_address + contract.encode_abi(
            "createAccount",
            args=[Web3.to_checksum_address(owner), salt],
        ).hex()

    def get_account_info(self, address: str) -> AAWalletInfo:
        """Get smart account information."""
        code = self.w3.eth.get_code(address)
        balance = self.w3.eth.get_balance(address)
        return AAWalletInfo(
            address=address,
            owner="",  # Read from account storage
            factory=self.factory_address,
            deployed=len(code) > 2,
            nonce=0,
            balance=float(self.w3.from_wei(balance, "ether")),
        )


__all__ = [
    "AAWallet",
    "AAPaymaster",
    "UserOperation",
    "UserOpResult",
    "AAWalletInfo",
    "AAChain",
    "ENTRY_POINTS",
    "BUNDLER_RPCS",
    "KNOWN_FACTORIES",
]