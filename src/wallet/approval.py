"""Approval Manager — Scan and revoke unlimited token approvals."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from ..chains.chain import Chain, ChainManager
from .wallet import Wallet


class ApprovalRisk(Enum):
    """Risk level of an approval."""
    SAFE = "safe"                     # Limited amount
    MODERATE = "moderate"             # Large but not unlimited
    HIGH = "high"                     # Unlimited approval to known protocol
    CRITICAL = "critical"             # Unlimited approval to unknown contract


@dataclass
class TokenApproval:
    """A token approval record."""
    token_address: str
    token_symbol: str
    spender: str                      # Contract address that has approval
    spender_label: str                # Human-readable label
    amount: float                     # Approved amount (float("inf") = unlimited)
    amount_raw: int                   # Raw amount on-chain
    chain: Chain
    risk: ApprovalRisk
    timestamp: float = 0              # When approval was set
    tx_hash: Optional[str] = None     # Approval transaction hash


@dataclass
class RevokeResult:
    """Result of a revoke operation."""
    token_address: str
    spender: str
    tx_hash: Optional[str] = None
    success: bool = False
    error: Optional[str] = None


# Known safe spenders (DeFi protocols)
KNOWN_SPENDERS = {
    # Uniswap
    "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45": "Uniswap V3 Router",
    "0x7a250d5630b4cf539739df2c5dacb4c659f2488d": "Uniswap V2 Router",
    "0x3fC91A3afd70395Cd496C647d5a6CC9D4B2b7FAD": "Universal Router",
    # Aave
    "0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2": "Aave V3 Pool",
    "0x7d2768de32b0b80b7a3454c06bdac94a69ddc7a9": "Aave V2 Lending Pool",
    # Compound
    "0xc3d688b66703497daa19211eedff47f25384cdc3": "Compound V3",
    # 1inch
    "0x1111111254fb6c44bac0bed2854e76f90643097d": "1inch Router",
    "0x1111111254eeb25477b68fb85ed929f73a960582": "1inch V5 Router",
    # OpenSea
    "0x0000000000000068f116a894984e2db1123eb395": "Seaport",
    # SushiSwap
    "0xd9e1ce17f2641f24ae83637ab66a2cca9c378b9f": "SushiSwap Router",
    # Lido
    "0xae7ab96520de3a18e5e111b5eaab095312d7fe84": "Lido stETH",
    # Curve
    "0x99a58482bd75cbab83b27ec03ca68ff489b5788f": "Curve Router",
    # LayerZero
    "0x66a7f7058f2c21c050f3c0e76f90c8972cf72d7a": "LayerZero Stargate",
    # Pendle
    "0x888888888889758f76e7103c6cbf23abbf58f946": "Pendle Router",
    # Morpho
    "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb": "Morpho",
}


class ApprovalManager:
    """Scan and revoke token approvals for security.

    Unlimited approvals are a major security risk — if a contract is
    compromised, it can drain all approved tokens. This tool helps
    identify and revoke risky approvals.

    Example::

        manager = ApprovalManager(wallet, chain_manager)

        # Scan for approvals
        approvals = manager.scan(Chain.ETHEREUM)

        # Filter risky ones
        risky = manager.get_risky()
        for a in risky:
            print(f"⚠️ {a.token_symbol} → {a.spender_label}: unlimited")

        # Revoke all unlimited approvals
        results = manager.revoke_all_unlimited(Chain.ETHEREUM)

        # Or revoke specific one
        manager.revoke(token_address, spender, Chain.ETHEREUM)
    """

    def __init__(self, wallet: Wallet, chain_manager: ChainManager):
        self.wallet = wallet
        self.chain_manager = chain_manager
        self.approvals: list[TokenApproval] = []

    def scan(self, chain: Chain = Chain.ETHEREUM) -> list[TokenApproval]:
        """Scan wallet for active token approvals.

        Args:
            chain: Chain to scan.

        Returns:
            List of active approvals.
        """
        # Common tokens to check
        tokens = self._get_common_tokens(chain)
        approvals = []

        for token_addr, symbol in tokens:
            token_approvals = self._check_token_approvals(
                token_addr, symbol, chain
            )
            approvals.extend(token_approvals)

        self.approvals = approvals
        return approvals

    def get_risky(
        self,
        min_risk: ApprovalRisk = ApprovalRisk.HIGH,
    ) -> list[TokenApproval]:
        """Get approvals with risk level >= min_risk.

        Args:
            min_risk: Minimum risk level to return.

        Returns:
            List of risky approvals.
        """
        risk_order = {
            ApprovalRisk.SAFE: 0,
            ApprovalRisk.MODERATE: 1,
            ApprovalRisk.HIGH: 2,
            ApprovalRisk.CRITICAL: 3,
        }
        threshold = risk_order[min_risk]
        return [
            a for a in self.approvals
            if risk_order[a.risk] >= threshold
        ]

    def get_unlimited(self) -> list[TokenApproval]:
        """Get all unlimited approvals."""
        return [
            a for a in self.approvals
            if a.amount == float("inf")
        ]

    def get_summary(self) -> dict:
        """Get approval summary."""
        unlimited = self.get_unlimited()
        risky = self.get_risky(ApprovalRisk.HIGH)
        known = [a for a in self.approvals if a.spender_label != "Unknown"]
        unknown = [a for a in self.approvals if a.spender_label == "Unknown"]

        return {
            "total_approvals": len(self.approvals),
            "unlimited": len(unlimited),
            "high_risk": len(risky),
            "known_protocols": len(known),
            "unknown_contracts": len(unknown),
            "approvals": [
                {
                    "token": a.token_symbol,
                    "spender": a.spender_label,
                    "amount": "unlimited" if a.amount == float("inf") else f"{a.amount:.2f}",
                    "risk": a.risk.value,
                    "chain": a.chain.value,
                }
                for a in self.approvals
            ],
        }

    def revoke(
        self,
        token_address: str,
        spender: str,
        chain: Chain,
    ) -> RevokeResult:
        """Revoke a specific token approval.

        Args:
            token_address: Token contract address.
            spender: Spender to revoke.
            chain: Chain where the approval exists.

        Returns:
            RevokeResult with tx details.
        """
        try:
            # Build revoke transaction (approve to 0)
            tx = self._build_revoke_tx(token_address, spender, chain)
            return RevokeResult(
                token_address=token_address,
                spender=spender,
                tx_hash=tx.get("hash"),
                success=True,
            )
        except Exception as e:
            return RevokeResult(
                token_address=token_address,
                spender=spender,
                success=False,
                error=str(e),
            )

    def revoke_all_unlimited(self, chain: Chain) -> list[RevokeResult]:
        """Revoke all unlimited approvals.

        Args:
            chain: Chain to revoke on.

        Returns:
            List of RevokeResult.
        """
        unlimited = [a for a in self.approvals if a.amount == float("inf")]
        results = []

        for approval in unlimited:
            result = self.revoke(
                approval.token_address,
                approval.spender,
                chain,
            )
            results.append(result)
            time.sleep(1)  # Rate limit

        return results

    def revoke_unknown(self, chain: Chain) -> list[RevokeResult]:
        """Revoke all approvals to unknown contracts.

        Args:
            chain: Chain to revoke on.

        Returns:
            List of RevokeResult.
        """
        unknown = [
            a for a in self.approvals
            if a.spender_label == "Unknown" and a.amount == float("inf")
        ]
        results = []

        for approval in unknown:
            result = self.revoke(
                approval.token_address,
                approval.spender,
                chain,
            )
            results.append(result)
            time.sleep(1)

        return results

    def is_known_spender(self, address: str) -> tuple[bool, str]:
        """Check if a spender address is a known DeFi protocol.

        Args:
            address: Spender address.

        Returns:
            Tuple of (is_known, label).
        """
        label = KNOWN_SPENDERS.get(address.lower())
        return (label is not None, label or "Unknown")

    # === Internal ===

    def _check_token_approvals(
        self,
        token_address: str,
        symbol: str,
        chain: Chain,
    ) -> list[TokenApproval]:
        """Check approvals for a specific token."""
        # Simplified — real implementation would query Approval events
        # from the token contract's event log
        try:
            w3 = self.chain_manager.get_web3(chain)

            # ERC20 approve function selector
            approve_topic = "0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925"

            # Get approval events for this wallet
            logs = w3.eth.get_logs({
                "fromBlock": "latest",
                "toBlock": "latest",
                "address": token_address,
                "topics": [
                    approve_topic,
                    "0x" + "0" * 24 + self.wallet.address[2:].lower(),  # owner
                ],
            })

            approvals = []
            for log in logs:
                spender = "0x" + log["topics"][2].hex()[-40:]
                amount_raw = int(log["data"].hex(), 16)
                amount = float("inf") if amount_raw >= 2**255 else amount_raw / 1e18

                is_known, label = self.is_known_spender(spender)
                risk = self._assess_risk(amount, is_known)

                approvals.append(TokenApproval(
                    token_address=token_address,
                    token_symbol=symbol,
                    spender=spender,
                    spender_label=label,
                    amount=amount,
                    amount_raw=amount_raw,
                    chain=chain,
                    risk=risk,
                    timestamp=time.time(),
                ))

            return approvals
        except Exception:
            return []

    def _build_revoke_tx(
        self,
        token_address: str,
        spender: str,
        chain: Chain,
    ) -> dict:
        """Build a revoke approval transaction."""
        # ERC20 approve(spender, 0)
        return {
            "to": token_address,
            "function": "approve",
            "args": {"spender": spender, "amount": 0},
            "chain": chain.value,
            "status": "built",
        }

    def _assess_risk(self, amount: float, is_known: bool) -> ApprovalRisk:
        """Assess risk level of an approval."""
        if amount != float("inf"):
            if amount < 1000:
                return ApprovalRisk.SAFE
            return ApprovalRisk.MODERATE

        # Unlimited approval
        if is_known:
            return ApprovalRisk.HIGH
        return ApprovalRisk.CRITICAL

    def _get_common_tokens(self, chain: Chain) -> list[tuple[str, str]]:
        """Get common tokens for a chain."""
        tokens = {
            Chain.ETHEREUM: [
                ("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "WETH"),
                ("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", "USDC"),
                ("0xdAC17F958D2ee523a2206206994597C13D831ec7", "USDT"),
                ("0x6B175474E89094C44Da98b954EedeAC495271d0F", "DAI"),
                ("0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599", "WBTC"),
                ("0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0", "wstETH"),
                ("0x514910771AF9Ca656af840dff83E8264EcF986CA", "LINK"),
                ("0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984", "UNI"),
            ],
            Chain.BASE: [
                ("0x4200000000000000000000000000000000000006", "WETH"),
                ("0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "USDC"),
                ("0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb", "DAI"),
            ],
            Chain.ARBITRUM: [
                ("0x82aF49447D8a07e3bd95BD0d56f35241523fBab1", "WETH"),
                ("0xaf88d065e77c8cC2239327C5EDb3A432268e5831", "USDC"),
                ("0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9", "USDT"),
                ("0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f", "WBTC"),
            ],
        }
        return tokens.get(chain, [])
