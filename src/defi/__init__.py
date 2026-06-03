"""DeFi protocol integrations — Uniswap, Aave, Curve, and more."""

from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

from ..wallet import Wallet
from ..chain import Chain, ChainManager, CHAIN_IDS

logger = logging.getLogger(__name__)


# Uniswap V2 Router ABI (minimal)
UNISWAP_V2_ROUTER_ABI = json.loads("""[
    {
        "inputs": [
            {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
            {"internalType": "address[]", "name": "path", "type": "address[]"},
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "deadline", "type": "uint256"}
        ],
        "name": "swapExactETHForTokens",
        "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
            {"internalType": "address[]", "name": "path", "type": "address[]"},
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "deadline", "type": "uint256"}
        ],
        "name": "swapExactTokensForETH",
        "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
            {"internalType": "address[]", "name": "path", "type": "address[]"},
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "deadline", "type": "uint256"}
        ],
        "name": "swapExactTokensForTokens",
        "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "address[]", "name": "path", "type": "address[]"}
        ],
        "name": "getAmountsOut",
        "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
        "stateMutability": "view",
        "type": "function"
    }
]""")

# ERC20 ABI (minimal for approve + balanceOf)
ERC20_ABI = json.loads("""[
    {
        "inputs": [
            {"internalType": "address", "name": "spender", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"}
        ],
        "name": "approve",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function"
    }
]""")

# WETH addresses
WETH = {
    Chain.ETHEREUM: "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
    Chain.BASE: "0x4200000000000000000000000000000000000006",
    Chain.ARBITRUM: "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
    Chain.OPTIMISM: "0x4200000000000000000000000000000000000006",
    Chain.POLYGON: "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",
}

# Native token address (ETH/MATIC/etc)
NATIVE = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"

# Common stablecoin addresses per chain
STABLECOINS = {
    Chain.ETHEREUM: {
        "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
        "DAI": "0x6B175474E89094C44Da98b954EedeAC495271d0F",
    },
    Chain.BASE: {
        "USDC": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        "USDbC": "0xd9aAEc86B65D86f6A7B5B1b0c42FFA531710b6CA",
    },
    Chain.ARBITRUM: {
        "USDC": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
        "USDT": "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9",
    },
}


@dataclass
class SwapResult:
    """Result of a token swap."""

    tx_hash: str
    token_in: str
    token_out: str
    amount_in: float
    amount_out: float
    gas_used: int
    chain: Chain


@dataclass
class YieldOpportunity:
    """A yield farming opportunity."""

    protocol: str
    pool: str
    apy: float
    tvl: float
    chain: Chain
    risk_score: float


class DeFiTool(ABC):
    """Base class for DeFi protocol integrations."""

    name: str = "base"
    supported_chains: list[Chain] = []

    @abstractmethod
    def execute(self, wallet: Wallet, **kwargs) -> Any:
        """Execute a DeFi operation."""
        pass


class Uniswap(DeFiTool):
    """Uniswap V2 DEX integration — actual swap execution."""

    name = "uniswap"
    supported_chains = [Chain.ETHEREUM, Chain.BASE, Chain.ARBITRUM, Chain.OPTIMISM, Chain.POLYGON]

    # V2 Router addresses
    ROUTERS = {
        Chain.ETHEREUM: "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D",
        Chain.BASE: "0x4752ba5DBc23f44D87826276BF6Fd6b1C372aD24",
        Chain.ARBITRUM: "0x4752ba5DBc23f44D87826276BF6Fd6b1C372aD24",
        Chain.OPTIMISM: "0x4752ba5DBc23f44D87826276BF6Fd6b1C372aD24",
        Chain.POLYGON: "0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff",
    }

    def __init__(self, chain_manager: Optional[ChainManager] = None, slippage: float = 0.5):
        self.chain_manager = chain_manager
        self.slippage = slippage  # percent

    def execute(self, wallet: Wallet, token_in: str, token_out: str, amount: float,
                chain: Chain = Chain.ETHEREUM, **kwargs) -> SwapResult:
        """
        Execute a token swap on Uniswap V2.

        Args:
            wallet: Wallet to swap from
            token_in: Input token address (or "ETH"/"NATIVE" for native token)
            token_out: Output token address (or "ETH"/"NATIVE" for native token)
            amount: Amount of input token (in human-readable units, e.g. 0.1 for 0.1 ETH)
            chain: Chain to swap on

        Returns:
            SwapResult with tx hash and details
        """
        if chain not in self.ROUTERS:
            raise ValueError(f"Uniswap not supported on {chain.value}")

        if not self.chain_manager:
            raise ValueError("ChainManager required for swap execution")

        w3 = self.chain_manager.get_web3(chain)
        router_addr = self.ROUTERS[chain]
        router = w3.eth.contract(address=w3.to_checksum_address(router_addr), abi=UNISWAP_V2_ROUTER_ABI)

        # Resolve token addresses
        weth_addr = WETH.get(chain)
        is_eth_in = token_in.upper() in ("ETH", "NATIVE", weth_addr)
        is_eth_out = token_out.upper() in ("ETH", "NATIVE", weth_addr)

        if is_eth_in:
            token_in_addr = weth_addr
        else:
            token_in_addr = w3.to_checksum_address(token_in)

        if is_eth_out:
            token_out_addr = weth_addr
        else:
            token_out_addr = w3.to_checksum_address(token_out)

        # Build swap path
        path = [w3.to_checksum_address(token_in_addr), w3.to_checksum_address(token_out_addr)]

        # Get decimals for amount conversion
        if is_eth_in:
            decimals = 18
        else:
            token_contract = w3.eth.contract(address=token_in_addr, abi=ERC20_ABI)
            decimals = token_contract.functions.decimals().call()

        amount_wei = int(amount * (10 ** decimals))

        # Get quote
        amounts_out = router.functions.getAmountsOut(amount_wei, path).call()
        amount_out_raw = amounts_out[-1]

        # Get output decimals
        if is_eth_out:
            out_decimals = 18
        else:
            out_contract = w3.eth.contract(address=token_out_addr, abi=ERC20_ABI)
            out_decimals = out_contract.functions.decimals().call()

        amount_out = amount_out_raw / (10 ** out_decimals)
        amount_out_min = int(amount_out_raw * (1 - self.slippage / 100))

        # Deadline: 20 minutes from now
        deadline = int(time.time()) + 1200

        # Get nonce and gas price
        nonce = w3.eth.get_transaction_count(wallet.address)
        gas_price = w3.eth.gas_price

        # Build transaction based on swap direction
        if is_eth_in:
            # swapExactETHForTokens
            tx = router.functions.swapExactETHForTokens(
                amount_out_min,
                path,
                w3.to_checksum_address(wallet.address),
                deadline,
            ).build_transaction({
                "from": w3.to_checksum_address(wallet.address),
                "value": amount_wei,
                "gas": 250000,
                "gasPrice": gas_price,
                "nonce": nonce,
                "chainId": CHAIN_IDS.get(chain, 1),
            })
        elif is_eth_out:
            # swapExactTokensForETH — need approval first
            self._approve_token(wallet, token_in_addr, router_addr, amount_wei, w3, chain, nonce)
            nonce += 1

            tx = router.functions.swapExactTokensForETH(
                amount_wei,
                amount_out_min,
                path,
                w3.to_checksum_address(wallet.address),
                deadline,
            ).build_transaction({
                "from": w3.to_checksum_address(wallet.address),
                "gas": 250000,
                "gasPrice": gas_price,
                "nonce": nonce,
                "chainId": CHAIN_IDS.get(chain, 1),
            })
        else:
            # swapExactTokensForTokens — need approval first
            self._approve_token(wallet, token_in_addr, router_addr, amount_wei, w3, chain, nonce)
            nonce += 1

            tx = router.functions.swapExactTokensForTokens(
                amount_wei,
                amount_out_min,
                path,
                w3.to_checksum_address(wallet.address),
                deadline,
            ).build_transaction({
                "from": w3.to_checksum_address(wallet.address),
                "gas": 250000,
                "gasPrice": gas_price,
                "nonce": nonce,
                "chainId": CHAIN_IDS.get(chain, 1),
            })

        # Sign and send
        signed = wallet.sign_transaction(tx, chain)
        tx_hash = w3.eth.send_raw_transaction(signed)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

        return SwapResult(
            tx_hash=tx_hash.hex(),
            token_in=token_in,
            token_out=token_out,
            amount_in=amount,
            amount_out=amount_out,
            gas_used=receipt.gasUsed,
            chain=chain,
        )

    def get_quote(self, token_in: str, token_out: str, amount: float,
                  chain: Chain = Chain.ETHEREUM) -> dict:
        """
        Get a swap quote without executing.

        Args:
            token_in: Input token address (or "ETH" for native)
            token_out: Output token address (or "ETH" for native)
            amount: Amount in human-readable units
            chain: Chain to quote on

        Returns:
            Dict with amount_out, price_impact, etc.
        """
        if chain not in self.ROUTERS:
            raise ValueError(f"Uniswap not supported on {chain.value}")

        if not self.chain_manager:
            raise ValueError("ChainManager required for quote")

        w3 = self.chain_manager.get_web3(chain)
        router_addr = self.ROUTERS[chain]
        router = w3.eth.contract(address=w3.to_checksum_address(router_addr), abi=UNISWAP_V2_ROUTER_ABI)

        weth_addr = WETH.get(chain)
        is_eth_in = token_in.upper() in ("ETH", "NATIVE", weth_addr)
        is_eth_out = token_out.upper() in ("ETH", "NATIVE", weth_addr)

        token_in_addr = weth_addr if is_eth_in else w3.to_checksum_address(token_in)
        token_out_addr = weth_addr if is_eth_out else w3.to_checksum_address(token_out)

        path = [w3.to_checksum_address(token_in_addr), w3.to_checksum_address(token_out_addr)]

        if is_eth_in:
            decimals = 18
        else:
            token_contract = w3.eth.contract(address=token_in_addr, abi=ERC20_ABI)
            decimals = token_contract.functions.decimals().call()

        amount_wei = int(amount * (10 ** decimals))

        try:
            amounts_out = router.functions.getAmountsOut(amount_wei, path).call()
            amount_out_raw = amounts_out[-1]

            if is_eth_out:
                out_decimals = 18
            else:
                out_contract = w3.eth.contract(address=token_out_addr, abi=ERC20_ABI)
                out_decimals = out_contract.functions.decimals().call()

            amount_out = amount_out_raw / (10 ** out_decimals)
            price = amount_out / amount if amount > 0 else 0

            return {
                "amount_in": amount,
                "amount_out": amount_out,
                "price": price,
                "path": path,
                "chain": chain.value,
            }
        except Exception as e:
            return {"error": str(e), "chain": chain.value}

    def _approve_token(self, wallet: Wallet, token_addr: str, spender: str,
                       amount: int, w3, chain: Chain, nonce: int):
        """Approve token spending for router."""
        token = w3.eth.contract(address=w3.to_checksum_address(token_addr), abi=ERC20_ABI)

        # Check current allowance
        allowance = token.functions.allowance(
            w3.to_checksum_address(wallet.address),
            w3.to_checksum_address(spender)
        ).call()

        if allowance >= amount:
            logger.info(f"Token already approved ({allowance} >= {amount})")
            return

        # Build approve tx
        approve_tx = token.functions.approve(
            w3.to_checksum_address(spender),
            2**256 - 1  # Max approval
        ).build_transaction({
            "from": w3.to_checksum_address(wallet.address),
            "gas": 100000,
            "gasPrice": w3.eth.gas_price,
            "nonce": nonce,
            "chainId": CHAIN_IDS.get(chain, 1),
        })

        signed = wallet.sign_transaction(approve_tx, chain)
        tx_hash = w3.eth.send_raw_transaction(signed)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
        logger.info(f"Token approved: {tx_hash.hex()} (gas: {receipt.gasUsed})")

    def resolve_token(self, symbol: str, chain: Chain) -> str:
        """Resolve token symbol to address."""
        symbol = symbol.upper()
        if symbol in ("ETH", "NATIVE", "MATIC"):
            return NATIVE
        if chain in STABLECOINS and symbol in STABLECOINS[chain]:
            return STABLECOINS[chain][symbol]
        if chain in WETH and symbol == "WETH":
            return WETH[chain]
        raise ValueError(f"Unknown token symbol: {symbol} on {chain.value}")


class Aerodrome(DeFiTool):
    """Aerodrome DEX on Base."""

    name = "aerodrome"
    supported_chains = [Chain.BASE]

    ROUTER = "0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43"

    def __init__(self, chain_manager: Optional[ChainManager] = None, slippage: float = 0.5):
        self.chain_manager = chain_manager
        self.slippage = slippage

    def execute(self, wallet: Wallet, token_in: str, token_out: str, amount: float, **kwargs) -> SwapResult:
        """Execute a swap on Aerodrome (uses Uniswap V2-compatible router)."""
        # Aerodrome uses a V2-compatible router, so we reuse Uniswap logic
        uniswap = Uniswap(chain_manager=self.chain_manager, slippage=self.slippage)
        uniswap.ROUTERS[Chain.BASE] = self.ROUTER
        return uniswap.execute(wallet, token_in, token_out, amount, chain=Chain.BASE, **kwargs)


class Aave(DeFiTool):
    """Aave lending/borrowing protocol integration."""

    name = "aave"
    supported_chains = [Chain.ETHEREUM, Chain.BASE, Chain.ARBITRUM, Chain.OPTIMISM, Chain.POLYGON]

    def execute(self, wallet: Wallet, action: str, **kwargs) -> Any:
        """Execute an Aave operation (supply, borrow, withdraw, repay)."""
        raise NotImplementedError("Aave operations not yet implemented")

    def get_yield_opportunities(self, chain: Chain) -> list[YieldOpportunity]:
        """Get available yield opportunities."""
        raise NotImplementedError("Aave yield query not yet implemented")


class Curve(DeFiTool):
    """Curve Finance stableswap integration."""

    name = "curve"
    supported_chains = [Chain.ETHEREUM, Chain.ARBITRUM, Chain.POLYGON]

    def execute(self, wallet: Wallet, pool: str, token_in: str, token_out: str, amount: float, **kwargs) -> SwapResult:
        """Execute a swap on Curve."""
        raise NotImplementedError("Curve swap not yet implemented")
