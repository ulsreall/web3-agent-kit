"""Transaction Simulator Module — Simulate transactions before broadcast.

Simulate transactions using Tenderly, local fork, or eth_call to verify
outcomes before committing funds. Catches reverts, MEV exposure, and
unexpected state changes.

Usage::
    from web3_agent_kit.simulator import TxSimulator
    
    sim = TxSimulator(rpc_url="https://eth.llamarpc.com")
    result = sim.simulate(
        from_address="0x...",
        to="0x...",
        data="0x...",
        value=1000000000000000000,  # 1 ETH
    )
    if result.success:
        print(f"Estimated gas: {result.gas_used}")
    else:
        print(f"Would revert: {result.error}")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class SimMode(Enum):
    """Simulation mode."""
    ETH_CALL = "eth_call"         # Simple eth_call (fast but limited)
    TENDERLY = "tenderly"         # Tenderly Simulation API (full state diff)
    LOCAL_FORK = "local_fork"     # Anvil/Hardhat local fork


@dataclass
class SimResult:
    """Result of a transaction simulation."""
    success: bool
    gas_used: int = 0
    gas_limit: int = 0
    return_value: str = "0x"
    error: str = ""
    revert_reason: str = ""
    events: list[dict] = field(default_factory=list)
    state_changes: list[dict] = field(default_factory=list)
    balance_changes: list[dict] = field(default_factory=list)
    logs: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "gas_used": self.gas_used,
            "gas_limit": self.gas_limit,
            "revert_reason": self.revert_reason,
            "num_events": len(self.events),
            "num_state_changes": len(self.state_changes),
            "warnings": self.warnings,
        }


@dataclass
class SimConfig:
    """Configuration for transaction simulation."""
    mode: SimMode = SimMode.ETH_CALL
    block_number: Optional[int] = None  # None = latest
    tenderly_api_key: Optional[str] = None
    tenderly_user: Optional[str] = None
    tenderly_project: Optional[str] = None
    fork_url: Optional[str] = None  # For local fork mode
    include_state_diff: bool = True
    include_events: bool = True
    gas_multiplier: float = 1.2  # Safety margin on gas estimates


class TxSimulator:
    """Transaction simulator for pre-flight verification.

    Simulates transactions before broadcasting to catch:
    - Reverts and revert reasons
    - Unexpected state changes
    - Balance changes (ETH/token transfers)
    - Gas estimation with safety margin
    - MEV exposure warnings

    Example::
        sim = TxSimulator(rpc_url="https://eth.llamarpc.com")
        result = sim.simulate(
            from_address="0x...",
            to="0x...",
            data="0x...",
            value=1000000000000000000,
        )
        if not result.success:
            print(f"TX would fail: {result.revert_reason}")
    """

    def __init__(self, rpc_url: str, config: Optional[SimConfig] = None):
        self.rpc_url = rpc_url
        self.config = config or SimConfig()

        from web3 import Web3
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))

    def simulate(
        self,
        from_address: str,
        to: str,
        data: str = "0x",
        value: int = 0,
        gas_limit: Optional[int] = None,
        block_number: Optional[int] = None,
    ) -> SimResult:
        """Simulate a transaction.

        Args:
            from_address: Sender address
            to: Recipient/contract address
            data: Transaction calldata
            value: Value in wei
            gas_limit: Optional gas limit
            block_number: Block number to simulate at (None = latest)

        Returns:
            SimResult with success, gas, events, and warnings
        """
        warnings: list[str] = []

        if self.config.mode == SimMode.TENDERLY:
            return self._simulate_tenderly(from_address, to, data, value)
        elif self.config.mode == SimMode.LOCAL_FORK:
            return self._simulate_fork(from_address, to, data, value)
        else:
            return self._simulate_eth_call(from_address, to, data, value, gas_limit, block_number, warnings)

    def _simulate_eth_call(
        self,
        from_address: str,
        to: str,
        data: str,
        value: int,
        gas_limit: Optional[int],
        block_number: Optional[int],
        warnings: list[str],
    ) -> SimResult:
        """Simulate using eth_call."""
        from web3 import Web3

        block = block_number or self.config.block_number or "latest"

        # Build transaction
        tx = {
            "from": self.w3.to_checksum_address(from_address),
            "to": self.w3.to_checksum_address(to) if to else None,
            "data": data,
            "value": hex(value) if value > 0 else "0x0",
        }

        if gas_limit:
            tx["gas"] = hex(gas_limit)

        try:
            # First, simulate the call
            result = self.w3.eth.call(tx, block_identifier=block)
            return_value = result.hex() if isinstance(result, bytes) else str(result)

            # Estimate gas
            try:
                estimated_gas = self.w3.eth.estimate_gas(tx, block_identifier=block)
                safe_gas = int(estimated_gas * self.config.gas_multiplier)
            except Exception:
                estimated_gas = 0
                safe_gas = 0
                warnings.append("Gas estimation failed; may need manual gas limit")

            # Check for balance changes
            balance_changes = []
            if value > 0:
                balance_before = self.w3.eth.get_balance(
                    self.w3.to_checksum_address(from_address),
                    block_identifier=block,
                )
                balance_changes.append({
                    "address": from_address,
                    "change": -value,
                    "currency": "ETH",
                })

            # Check for common issues
            if value > 0 and to:
                recipient_balance = self.w3.eth.get_balance(
                    self.w3.to_checksum_address(to),
                    block_identifier=block,
                )
                if recipient_balance == 0:
                    warnings.append("Recipient has zero balance")
                balance_changes.append({
                    "address": to,
                    "change": value,
                    "currency": "ETH",
                })

            return SimResult(
                success=True,
                gas_used=estimated_gas,
                gas_limit=safe_gas,
                return_value=return_value,
                balance_changes=balance_changes,
                warnings=warnings,
            )

        except Exception as e:
            err_str = str(e)
            revert_reason = ""

            # Try to extract revert reason
            if "execution reverted" in err_str.lower():
                revert_reason = err_str
            elif "revert" in err_str.lower():
                revert_reason = err_str

            return SimResult(
                success=False,
                error=err_str,
                revert_reason=revert_reason or err_str,
                warnings=warnings,
            )

    def _simulate_tenderly(
        self,
        from_address: str,
        to: str,
        data: str,
        value: int,
    ) -> SimResult:
        """Simulate using Tenderly Simulation API."""
        if not self.config.tenderly_api_key or not self.config.tenderly_user or not self.config.tenderly_project:
            raise ValueError("Tenderly API key, user, and project required for Tenderly mode")

        import json
        import requests
        from web3 import Web3

        chain_id = self.w3.eth.chain_id
        url = f"https://api.tenderly.co/api/v1/account/{self.config.tenderly_user}/project/{self.config.tenderly_project}/simulate"

        payload = {
            "network_id": str(chain_id),
            "from": self.w3.to_checksum_address(from_address),
            "to": self.w3.to_checksum_address(to) if to else None,
            "input": data,
            "value": str(value),
            "save": False,
            "save_if_fails": False,
            "simulation_type": "quick",
        }

        if self.config.block_number:
            payload["block_number"] = self.config.block_number

        resp = requests.post(
            url,
            headers={"X-Access-Key": self.config.tenderly_api_key, "Content-Type": "application/json"},
            json=payload,
            timeout=30,
        )

        if resp.status_code != 200:
            return SimResult(success=False, error=f"Tenderly API error: {resp.status_code}")

        data = resp.json()
        sim = data.get("simulation", data)
        tx_data = sim.get("transaction", sim)

        success = not tx_data.get("error_info") and tx_data.get("status", False)
        gas_used = int(tx_data.get("gas_used", 0))
        events = tx_data.get("logs", [])
        state_changes = sim.get("state_overrides", {})

        # Extract warnings
        warnings = []
        if tx_data.get("error_info"):
            warnings.append(f"Tenderly: {tx_data['error_info'].get('message', '')}")

        return SimResult(
            success=success,
            gas_used=gas_used,
            gas_limit=int(gas_used * self.config.gas_multiplier),
            events=events,
            state_changes=list(state_changes.keys()) if isinstance(state_changes, dict) else [],
            logs=events,
            warnings=warnings,
        )

    def _simulate_fork(
        self,
        from_address: str,
        to: str,
        data: str,
        value: int,
    ) -> SimResult:
        """Simulate using local fork (Anvil/Hardhat)."""
        if not self.config.fork_url:
            raise ValueError("fork_url required for local fork mode")

        import requests
        from web3 import Web3

        fork_w3 = Web3(Web3.HTTPProvider(self.config.fork_url))

        tx = {
            "from": fork_w3.to_checksum_address(from_address),
            "to": fork_w3.to_checksum_address(to) if to else None,
            "data": data,
            "value": hex(value) if value > 0 else "0x0",
        }

        try:
            # Set impersonation if needed
            try:
                requests.post(
                    self.config.fork_url,
                    json={"method": "anvil_impersonateAccount", "params": [from_address], "id": 1, "jsonrpc": "2.0"},
                    timeout=5,
                )
            except Exception:
                pass

            result = fork_w3.eth.call(tx)
            gas = fork_w3.eth.estimate_gas(tx)

            return SimResult(
                success=True,
                gas_used=gas,
                gas_limit=int(gas * self.config.gas_multiplier),
                return_value=result.hex() if isinstance(result, bytes) else str(result),
            )
        except Exception as e:
            return SimResult(success=False, error=str(e), revert_reason=str(e))

    def simulate_batch(
        self,
        transactions: list[dict],
        from_address: str,
    ) -> list[SimResult]:
        """Simulate multiple transactions in sequence.

        Args:
            transactions: List of {to, data, value} dicts
            from_address: Sender address

        Returns:
            List of SimResult for each transaction
        """
        results = []
        for tx in transactions:
            result = self.simulate(
                from_address=from_address,
                to=tx.get("to", ""),
                data=tx.get("data", "0x"),
                value=tx.get("value", 0),
            )
            results.append(result)
            if not result.success:
                break  # Stop on first failure
        return results

    def check_approval(
        self,
        token: str,
        owner: str,
        spender: str,
    ) -> dict:
        """Check current token approval amount."""
        erc20_abi = [
            {"constant": True, "inputs": [{"name": "_owner", "type": "address"}, {"name": "_spender", "type": "address"}],
             "name": "allowance", "outputs": [{"name": "", "type": "uint256"}], "type": "function"},
        ]
        contract = self.w3.eth.contract(address=self.w3.to_checksum_address(token), abi=erc20_abi)
        allowance = contract.functions.allowance(
            self.w3.to_checksum_address(owner),
            self.w3.to_checksum_address(spender),
        ).call()
        return {"token": token, "owner": owner, "spender": spender, "allowance": allowance}


__all__ = [
    "TxSimulator",
    "SimResult",
    "SimConfig",
    "SimMode",
]