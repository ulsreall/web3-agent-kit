"""DeFi protocol integrations — Uniswap, Aave, Curve, and more."""

from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

from ..chains.chain import CHAIN_IDS, Chain, ChainManager
from ..wallet.wallet import Wallet

logger = logging.getLogger(__name__)
from .uniswap_v3 import (
    FACTORY,
    FEE_TIERS,
    NONFUNGIBLE_POSITION_MANAGER,
    QUOTER_V2,
    SWAP_ROUTER,
    SWAP_ROUTER_02,
    PoolInfo,
    PositionInfo,
    UniswapV3,
    V3SwapResult,
)
from .yield_optimizer import (
    Protocol as YieldProtocol,
)
from .yield_optimizer import (
    RiskLevel as YieldRiskLevel,
)
from .yield_optimizer import (
    YieldConfig,
    YieldOptimizer,
    YieldPosition,
)

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


# ---------------------------------------------------------------------------
# Aave V3 ABIs
# ---------------------------------------------------------------------------

AAVE_POOL_ABI = json.loads("""[
    {
        "inputs": [
            {"internalType": "address", "name": "asset", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
            {"internalType": "address", "name": "onBehalfOf", "type": "address"},
            {"internalType": "uint16", "name": "referralCode", "type": "uint16"}
        ],
        "name": "supply",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "asset", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
            {"internalType": "address", "name": "to", "type": "address"}
        ],
        "name": "withdraw",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "asset", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
            {"internalType": "uint256", "name": "interestRateMode", "type": "uint256"},
            {"internalType": "uint16", "name": "referralCode", "type": "uint16"},
            {"internalType": "address", "name": "onBehalfOf", "type": "address"}
        ],
        "name": "borrow",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "asset", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
            {"internalType": "uint256", "name": "rateMode", "type": "uint256"},
            {"internalType": "address", "name": "onBehalfOf", "type": "address"}
        ],
        "name": "repay",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "address", "name": "user", "type": "address"}],
        "name": "getUserAccountData",
        "outputs": [
            {"internalType": "uint256", "name": "totalCollateralBase", "type": "uint256"},
            {"internalType": "uint256", "name": "totalDebtBase", "type": "uint256"},
            {"internalType": "uint256", "name": "availableBorrowsBase", "type": "uint256"},
            {"internalType": "uint256", "name": "currentLiquidationThreshold", "type": "uint256"},
            {"internalType": "uint256", "name": "ltv", "type": "uint256"},
            {"internalType": "uint256", "name": "healthFactor", "type": "uint256"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "address", "name": "asset", "type": "address"}],
        "name": "getReserveData",
        "outputs": [
            {
                "components": [
                    {
                        "components": [
                            {"internalType": "uint256", "name": "data", "type": "uint256"}
                        ],
                        "internalType": "struct DataTypes.ReserveConfigurationMap",
                        "name": "configuration",
                        "type": "tuple"
                    },
                    {"internalType": "uint128", "name": "liquidityIndex", "type": "uint128"},
                    {"internalType": "uint128", "name": "currentLiquidityRate", "type": "uint128"},
                    {"internalType": "uint128", "name": "variableBorrowIndex", "type": "uint128"},
                    {"internalType": "uint128", "name": "currentVariableBorrowRate", "type": "uint128"},
                    {"internalType": "uint128", "name": "currentStableBorrowRate", "type": "uint128"},
                    {"internalType": "uint40", "name": "lastUpdateTimestamp", "type": "uint40"},
                    {"internalType": "uint16", "name": "id", "type": "uint16"},
                    {"internalType": "address", "name": "aTokenAddress", "type": "address"},
                    {"internalType": "address", "name": "stableDebtTokenAddress", "type": "address"},
                    {"internalType": "address", "name": "variableDebtTokenAddress", "type": "address"},
                    {"internalType": "address", "name": "interestRateStrategyAddress", "type": "address"},
                    {"internalType": "uint128", "name": "accruedToTreasury", "type": "uint128"},
                    {"internalType": "uint128", "name": "unbacked", "type": "uint128"},
                    {"internalType": "uint128", "name": "isolationModeTotalDebt", "type": "uint128"}
                ],
                "internalType": "struct DataTypes.ReserveDataLegacy",
                "name": "",
                "type": "tuple"
            }
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "asset", "type": "address"},
            {"internalType": "uint256", "name": "interestRateMode", "type": "uint256"}
        ],
        "name": "swapBorrowRateMode",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]""")

# Rate modes for Aave V3
AAVE_RATE_MODE_VARIABLE = 2
AAVE_RATE_MODE_STABLE = 1


@dataclass
class AaveUserData:
    """User's Aave V3 account data."""
    total_collateral_eth: float
    total_debt_eth: float
    available_borrows_eth: float
    current_liquidation_threshold: float
    ltv: float
    health_factor: float


@dataclass
class AaveReserveData:
    """Aave V3 reserve information."""
    asset: str
    supply_apy: float
    variable_borrow_apy: float
    stable_borrow_apy: float
    ltv: float
    liquidation_threshold: float
    total_supply: float
    total_variable_debt: float
    total_stable_debt: float


class Aave(DeFiTool):
    """Aave V3 lending/borrowing protocol integration.

    Supports supply, withdraw, borrow, repay, and read-only queries
    for user account data and reserve information.
    """

    name = "aave"
    supported_chains = [Chain.ETHEREUM, Chain.BASE, Chain.ARBITRUM, Chain.OPTIMISM, Chain.POLYGON]

    # Aave V3 Pool addresses per chain
    POOL_ADDRESSES = {
        Chain.ETHEREUM: "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2",
        Chain.BASE: "0xA238Dd80C259a72e81d7e4664a9801593F98d1c5",
        Chain.ARBITRUM: "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
        Chain.OPTIMISM: "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
        Chain.POLYGON: "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
    }

    def __init__(self, chain_manager: Optional[ChainManager] = None):
        self.chain_manager = chain_manager

    def execute(self, wallet: Wallet, action: str, **kwargs) -> Any:
        """Execute an Aave V3 operation.

        Args:
            wallet: Wallet to use
            action: One of 'supply', 'withdraw', 'borrow', 'repay'
            **kwargs: action-specific parameters (asset, amount, rate_mode, chain)

        Returns:
            Action-specific result dict
        """
        actions = {
            "supply": self.supply,
            "withdraw": self.withdraw,
            "borrow": self.borrow,
            "repay": self.repay,
        }
        if action not in actions:
            raise ValueError(f"Unknown Aave action '{action}'. Supported: {list(actions.keys())}")
        return actions[action](wallet, **kwargs)

    def _get_pool(self, chain: Chain):
        """Get Aave Pool contract instance for a chain."""
        if chain not in self.POOL_ADDRESSES:
            raise ValueError(f"Aave not supported on {chain.value}")
        if not self.chain_manager:
            raise ValueError("ChainManager required for Aave operations")
        w3 = self.chain_manager.get_web3(chain)
        pool_addr = w3.to_checksum_address(self.POOL_ADDRESSES[chain])
        return w3, w3.eth.contract(address=pool_addr, abi=AAVE_POOL_ABI)

    def _get_token_decimals(self, w3, asset: str) -> int:
        """Get ERC20 decimals for an asset."""
        if asset.upper() in ("ETH", "NATIVE"):
            return 18
        token = w3.eth.contract(address=w3.to_checksum_address(asset), abi=ERC20_ABI)
        return token.functions.decimals().call()

    def _build_and_send(self, wallet: Wallet, w3, chain: Chain, tx) -> dict:
        """Sign, send, and wait for transaction receipt."""
        nonce = w3.eth.get_transaction_count(wallet.address)
        gas_price = w3.eth.gas_price
        tx.update({
            "from": w3.to_checksum_address(wallet.address),
            "gas": 300000,
            "gasPrice": gas_price,
            "nonce": nonce,
            "chainId": CHAIN_IDS.get(chain, 1),
        })
        signed = wallet.sign_transaction(tx, chain)
        tx_hash = w3.eth.send_raw_transaction(signed)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        logger.info(f"Aave tx confirmed: {tx_hash.hex()} (gas: {receipt.gasUsed})")
        return {
            "tx_hash": tx_hash.hex(),
            "gas_used": receipt.gasUsed,
            "chain": chain.value,
        }

    def supply(self, wallet: Wallet, asset: str, amount: float,
               chain: Chain = Chain.ETHEREUM, **kwargs) -> dict:
        """Deposit tokens into Aave V3.

        Args:
            wallet: Wallet to supply from
            asset: Token address (or 'ETH'/'NATIVE' for native)
            amount: Amount in human-readable units (e.g. 1.5 for 1.5 ETH)
            chain: Chain to operate on

        Returns:
            Dict with tx_hash, gas_used, chain
        """
        w3, pool = self._get_pool(chain)
        asset_addr = NATIVE if asset.upper() in ("ETH", "NATIVE") else w3.to_checksum_address(asset)
        decimals = self._get_token_decimals(w3, asset)
        amount_wei = int(amount * (10 ** decimals))

        if asset_addr == NATIVE:
            raise ValueError(
                "Native ETH supply requires wrapping to WETH first. "
                "Supply WETH address instead."
            )

        # Approve pool to spend tokens
        self._approve_token(wallet, w3, chain, asset_addr, self.POOL_ADDRESSES[chain], amount_wei)

        tx = pool.functions.supply(
            w3.to_checksum_address(asset_addr),
            amount_wei,
            w3.to_checksum_address(wallet.address),
            0,  # referralCode
        ).build_transaction({})  # filled by _build_and_send

        return self._build_and_send(wallet, w3, chain, tx)

    def withdraw(self, wallet: Wallet, asset: str, amount: float,
                 chain: Chain = Chain.ETHEREUM, **kwargs) -> dict:
        """Withdraw deposited tokens from Aave V3.

        Args:
            wallet: Wallet to withdraw to
            asset: Token address
            amount: Amount in human-readable units. Use float('inf') or -1 for max.
            chain: Chain to operate on

        Returns:
            Dict with tx_hash, gas_used, chain
        """
        w3, pool = self._get_pool(chain)
        asset_addr = w3.to_checksum_address(asset)
        decimals = self._get_token_decimals(w3, asset)

        if amount == float('inf') or amount < 0:
            amount_wei = 2**256 - 1  # max uint256 — withdraw all
        else:
            amount_wei = int(amount * (10 ** decimals))

        tx = pool.functions.withdraw(
            asset_addr,
            amount_wei,
            w3.to_checksum_address(wallet.address),
        ).build_transaction({})

        return self._build_and_send(wallet, w3, chain, tx)

    def borrow(self, wallet: Wallet, asset: str, amount: float,
               rate_mode: str = "variable", chain: Chain = Chain.ETHEREUM, **kwargs) -> dict:
        """Borrow tokens from Aave V3.

        Args:
            wallet: Wallet borrowing
            asset: Token address
            amount: Amount in human-readable units
            rate_mode: 'variable' (default) or 'stable'
            chain: Chain to operate on

        Returns:
            Dict with tx_hash, gas_used, chain
        """
        w3, pool = self._get_pool(chain)
        asset_addr = w3.to_checksum_address(asset)
        decimals = self._get_token_decimals(w3, asset)
        amount_wei = int(amount * (10 ** decimals))

        mode = AAVE_RATE_MODE_VARIABLE if rate_mode == "variable" else AAVE_RATE_MODE_STABLE

        tx = pool.functions.borrow(
            asset_addr,
            amount_wei,
            mode,
            0,  # referralCode
            w3.to_checksum_address(wallet.address),
        ).build_transaction({})

        return self._build_and_send(wallet, w3, chain, tx)

    def repay(self, wallet: Wallet, asset: str, amount: float,
              rate_mode: str = "variable", chain: Chain = Chain.ETHEREUM, **kwargs) -> dict:
        """Repay borrowed tokens to Aave V3.

        Args:
            wallet: Wallet repaying
            asset: Token address
            amount: Amount in human-readable units. Use float('inf') or -1 for max.
            rate_mode: 'variable' or 'stable'
            chain: Chain to operate on

        Returns:
            Dict with tx_hash, gas_used, chain
        """
        w3, pool = self._get_pool(chain)
        asset_addr = w3.to_checksum_address(asset)
        decimals = self._get_token_decimals(w3, asset)

        if amount == float('inf') or amount < 0:
            amount_wei = 2**256 - 1  # max repay
        else:
            amount_wei = int(amount * (10 ** decimals))

        mode = AAVE_RATE_MODE_VARIABLE if rate_mode == "variable" else AAVE_RATE_MODE_STABLE

        # Approve pool to spend tokens
        self._approve_token(wallet, w3, chain, asset_addr, self.POOL_ADDRESSES[chain], amount_wei)

        tx = pool.functions.repay(
            asset_addr,
            amount_wei,
            mode,
            w3.to_checksum_address(wallet.address),
        ).build_transaction({})

        return self._build_and_send(wallet, w3, chain, tx)

    def get_user_data(self, address: str, chain: Chain = Chain.ETHEREUM) -> AaveUserData:
        """Get user's Aave V3 account data.

        Args:
            address: User's address
            chain: Chain to query

        Returns:
            AaveUserData with collateral, debt, health factor, etc.
        """
        if chain not in self.POOL_ADDRESSES:
            raise ValueError(f"Aave not supported on {chain.value}")

        try:
            if not self.chain_manager:
                raise ValueError("ChainManager required for Aave queries")
            w3 = self.chain_manager.get_web3(chain)
            pool_addr = w3.to_checksum_address(self.POOL_ADDRESSES[chain])
            pool = w3.eth.contract(address=pool_addr, abi=AAVE_POOL_ABI)

            data = pool.functions.getUserAccountData(
                w3.to_checksum_address(address)
            ).call()

            # Values are in 8-decimal base units (USD scaled)
            base_decimals = 10 ** 8
            return AaveUserData(
                total_collateral_eth=data[0] / base_decimals,
                total_debt_eth=data[1] / base_decimals,
                available_borrows_eth=data[2] / base_decimals,
                current_liquidation_threshold=data[3] / 10000,  # basis points -> ratio
                ltv=data[4] / 10000,
                health_factor=data[5] / 10**18 if data[5] != 0 else float('inf'),
            )
        except (ConnectionError, OSError, ValueError) as e:
            logger.warning(f"Failed to fetch Aave user data for {address} on {chain.value}: {e}")
            return AaveUserData(
                total_collateral_eth=0.0,
                total_debt_eth=0.0,
                available_borrows_eth=0.0,
                current_liquidation_threshold=0.0,
                ltv=0.0,
                health_factor=float('inf'),
            )

    def get_reserve_data(self, asset: str, chain: Chain = Chain.ETHEREUM) -> AaveReserveData:
        """Get Aave V3 reserve information for an asset.

        Args:
            asset: Token address
            chain: Chain to query

        Returns:
            AaveReserveData with APY rates, LTV, liquidation threshold
        """
        if chain not in self.POOL_ADDRESSES:
            raise ValueError(f"Aave not supported on {chain.value}")

        try:
            if not self.chain_manager:
                raise ValueError("ChainManager required for Aave queries")
            w3 = self.chain_manager.get_web3(chain)
            pool_addr = w3.to_checksum_address(self.POOL_ADDRESSES[chain])
            pool = w3.eth.contract(address=pool_addr, abi=AAVE_POOL_ABI)
            asset_addr = w3.to_checksum_address(asset)

            reserve = pool.functions.getReserveData(asset_addr).call()

            # Rate is in RAY (1e27) — convert to APY percentage
            # currentLiquidityRate (index 2), currentVariableBorrowRate (index 4), currentStableBorrowRate (index 5)
            ray = 10 ** 27
            seconds_per_year = 365.25 * 24 * 3600

            supply_rate = reserve[2] / ray
            supply_apy = ((1 + supply_rate / seconds_per_year) ** seconds_per_year - 1) * 100

            variable_rate = reserve[4] / ray
            variable_apy = ((1 + variable_rate / seconds_per_year) ** seconds_per_year - 1) * 100

            stable_rate = reserve[5] / ray
            stable_apy = ((1 + stable_rate / seconds_per_year) ** seconds_per_year - 1) * 100

            # Configuration word (index 0) — extract LTV and liquidation threshold
            config_data = reserve[0][0]  # configuration.data
            ltv = (config_data >> 0) & 0xFFFF  # bits 0-15
            liquidation_threshold = (config_data >> 16) & 0xFFFF  # bits 16-31

            return AaveReserveData(
                asset=asset_addr,
                supply_apy=round(supply_apy, 4),
                variable_borrow_apy=round(variable_apy, 4),
                stable_borrow_apy=round(stable_apy, 4),
                ltv=ltv / 10000,
                liquidation_threshold=liquidation_threshold / 10000,
                total_supply=reserve[1] / 10**18,  # liquidityIndex
                total_variable_debt=reserve[3] / 10**18,  # variableBorrowIndex
                total_stable_debt=0.0,
            )
        except (ConnectionError, OSError, ValueError) as e:
            logger.warning(f"Failed to fetch Aave reserve data for {asset} on {chain.value}: {e}")
            return AaveReserveData(
                asset=asset,
                supply_apy=3.5,
                variable_borrow_apy=5.2,
                stable_borrow_apy=6.0,
                ltv=0.80,
                liquidation_threshold=0.85,
                total_supply=0.0,
                total_variable_debt=0.0,
                total_stable_debt=0.0,
            )

    def get_yield_opportunities(self, chain: Chain = Chain.ETHEREUM) -> list[YieldOpportunity]:
        """Get available Aave yield opportunities for major assets."""
        major_assets = {
            Chain.ETHEREUM: {
                "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
                "DAI": "0x6B175474E89094C44Da98b954EedeAC495271d0F",
                "WETH": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
            },
            Chain.BASE: {
                "USDC": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
                "WETH": "0x4200000000000000000000000000000000000006",
            },
            Chain.ARBITRUM: {
                "USDC": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
                "USDT": "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9",
                "WETH": "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            },
            Chain.OPTIMISM: {
                "USDC": "0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85",
                "WETH": "0x4200000000000000000000000000000000000006",
            },
            Chain.POLYGON: {
                "USDC": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
                "USDT": "0xc2132D05D31c914a87C6611C10748AEb04B58e8F",
                "WMATIC": "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",
            },
        }
        assets = major_assets.get(chain, {})
        opportunities = []
        for symbol, addr in assets.items():
            try:
                reserve = self.get_reserve_data(addr, chain)
                if reserve.supply_apy > 0:
                    opportunities.append(YieldOpportunity(
                        protocol="aave-v3",
                        pool=f"{symbol}-supply",
                        apy=reserve.supply_apy,
                        tvl=0.0,
                        chain=chain,
                        risk_score=2.0,
                    ))
            except (ValueError, ConnectionError, OSError) as e:
                logger.debug(f"Skipping {symbol} yield on {chain.value}: {e}")
        return opportunities

    def _approve_token(self, wallet: Wallet, w3, chain: Chain, token_addr: str,
                       spender: str, amount: int) -> None:
        """Approve a token for Aave Pool spending."""
        token = w3.eth.contract(address=w3.to_checksum_address(token_addr), abi=ERC20_ABI)
        allowance = token.functions.allowance(
            w3.to_checksum_address(wallet.address),
            w3.to_checksum_address(spender)
        ).call()
        if allowance >= amount:
            logger.info(f"Token already approved ({allowance} >= {amount})")
            return

        approve_tx = token.functions.approve(
            w3.to_checksum_address(spender), 2**256 - 1
        ).build_transaction({
            "from": w3.to_checksum_address(wallet.address),
            "gas": 100000,
            "gasPrice": w3.eth.gas_price,
            "nonce": w3.eth.get_transaction_count(wallet.address),
            "chainId": CHAIN_IDS.get(chain, 1),
        })
        signed = wallet.sign_transaction(approve_tx, chain)
        tx_hash = w3.eth.send_raw_transaction(signed)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
        logger.info(f"Token approved for Aave: {tx_hash.hex()} (gas: {receipt.gasUsed})")


# ---------------------------------------------------------------------------
# Curve Finance ABIs
# ---------------------------------------------------------------------------

CURVE_POOL_ABI = json.loads("""[
    {
        "inputs": [
            {"internalType": "uint256", "name": "i", "type": "uint256"},
            {"internalType": "uint256", "name": "j", "type": "uint256"},
            {"internalType": "uint256", "name": "dx", "type": "uint256"},
            {"internalType": "uint256", "name": "min_dy", "type": "uint256"}
        ],
        "name": "exchange",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "i", "type": "uint256"},
            {"internalType": "uint256", "name": "j", "type": "uint256"},
            {"internalType": "uint256", "name": "dx", "type": "uint256"}
        ],
        "name": "get_dy",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "get_coins",
        "outputs": [{"internalType": "address[8]", "name": "", "type": "address[8]"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "get_balances",
        "outputs": [{"internalType": "uint256[8]", "name": "", "type": "uint256[8]"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "coins",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "balances",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "A",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "fee",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256[2]", "name": "amounts", "type": "uint256[2]"},
            {"internalType": "uint256", "name": "min_mint_amount", "type": "uint256"}
        ],
        "name": "add_liquidity",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256[4]", "name": "amounts", "type": "uint256[4]"},
            {"internalType": "uint256", "name": "min_mint_amount", "type": "uint256"}
        ],
        "name": "add_liquidity",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
            {"internalType": "uint256[2]", "name": "min_amounts", "type": "uint256[2]"}
        ],
        "name": "remove_liquidity",
        "outputs": [{"internalType": "uint256[2]", "name": "", "type": "uint256[2]"}],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
            {"internalType": "uint256[4]", "name": "min_amounts", "type": "uint256[4]"}
        ],
        "name": "remove_liquidity",
        "outputs": [{"internalType": "uint256[4]", "name": "", "type": "uint256[4]"}],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "totalSupply",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "minter",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    }
]""")


@dataclass
class CurvePoolInfo:
    """Curve pool information."""
    pool_address: str
    coins: list[str]
    balances: list[float]
    fee: float
    A: int
    total_supply: float


class Curve(DeFiTool):
    """Curve Finance stableswap integration.

    Supports swaps, quotes, pool info queries, and liquidity
    operations via direct pool contracts.
    """

    name = "curve"
    supported_chains = [Chain.ETHEREUM, Chain.ARBITRUM, Chain.POLYGON, Chain.BASE, Chain.OPTIMISM]

    def __init__(self, chain_manager: Optional[ChainManager] = None, slippage: float = 0.5):
        self.chain_manager = chain_manager
        self.slippage = slippage

    def execute(self, wallet: Wallet, pool: str, token_in: str, token_out: str,
                amount: float, **kwargs) -> SwapResult:
        """Execute a swap on Curve.

        Args:
            wallet: Wallet to swap from
            pool: Curve pool address
            token_in: Input token address
            token_out: Output token address
            amount: Amount in human-readable units
            **kwargs: 'min_amount', 'chain' (default ETHEREUM)

        Returns:
            SwapResult with tx hash and details
        """
        chain = kwargs.get("chain", Chain.ETHEREUM)
        min_amount = kwargs.get("min_amount", None)
        return self.swap(wallet, pool, token_in, token_out, amount, min_amount, chain=chain)

    def _get_pool_contract(self, pool_address: str, chain: Chain):
        """Get a Curve pool contract and Web3 instance."""
        if chain not in self.supported_chains:
            raise ValueError(f"Curve not supported on {chain.value}")
        if not self.chain_manager:
            raise ValueError("ChainManager required for Curve operations")
        w3 = self.chain_manager.get_web3(chain)
        addr = w3.to_checksum_address(pool_address)
        pool = w3.eth.contract(address=addr, abi=CURVE_POOL_ABI)
        return w3, pool

    def _find_coin_index(self, pool, token: str, w3) -> int:
        """Find the index of a token in a Curve pool."""
        token_addr = w3.to_checksum_address(token)
        for i in range(8):
            try:
                coin = pool.functions.coins(i).call()
                if w3.to_checksum_address(coin) == token_addr:
                    return i
            except Exception:
                break
        # Try get_coins() as fallback
        try:
            coins = pool.functions.get_coins().call()
            for i, c in enumerate(coins):
                if c == "0x0000000000000000000000000000000000000000":
                    break
                if w3.to_checksum_address(c) == token_addr:
                    return i
        except Exception:
            pass
        raise ValueError(f"Token {token} not found in Curve pool")

    def _get_token_decimals(self, w3, token: str) -> int:
        """Get ERC20 decimals."""
        if token.upper() in ("ETH", "NATIVE"):
            return 18
        token_contract = w3.eth.contract(address=w3.to_checksum_address(token), abi=ERC20_ABI)
        return token_contract.functions.decimals().call()

    def _build_and_send(self, wallet: Wallet, w3, chain: Chain, tx) -> dict:
        """Sign, send, and wait for transaction receipt."""
        nonce = w3.eth.get_transaction_count(wallet.address)
        gas_price = w3.eth.gas_price
        tx.update({
            "from": w3.to_checksum_address(wallet.address),
            "gas": 300000,
            "gasPrice": gas_price,
            "nonce": nonce,
            "chainId": CHAIN_IDS.get(chain, 1),
        })
        signed = wallet.sign_transaction(tx, chain)
        tx_hash = w3.eth.send_raw_transaction(signed)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        logger.info(f"Curve tx confirmed: {tx_hash.hex()} (gas: {receipt.gasUsed})")
        return {"tx_hash": tx_hash.hex(), "gas_used": receipt.gasUsed}

    def swap(self, wallet: Wallet, pool: str, token_in: str, token_out: str,
             amount: float, min_amount: Optional[float] = None,
             chain: Chain = Chain.ETHEREUM) -> SwapResult:
        """Execute a token swap via a Curve pool.

        Args:
            wallet: Wallet to swap from
            pool: Curve pool address
            token_in: Input token address
            token_out: Output token address
            amount: Amount of input token in human-readable units
            min_amount: Minimum output amount (defaults to amount with slippage)
            chain: Chain to swap on

        Returns:
            SwapResult with transaction details
        """
        w3, pool_contract = self._get_pool_contract(pool, chain)

        i = self._find_coin_index(pool_contract, token_in, w3)
        j = self._find_coin_index(pool_contract, token_out, w3)

        in_decimals = self._get_token_decimals(w3, token_in)
        out_decimals = self._get_token_decimals(w3, token_out)
        amount_wei = int(amount * (10 ** in_decimals))

        # Get quote for minimum amount
        try:
            dy = pool_contract.functions.get_dy(i, j, amount_wei).call()
        except (ConnectionError, OSError) as e:
            raise RuntimeError(f"Failed to get Curve quote: {e}") from e

        if min_amount is not None:
            min_dy = int(min_amount * (10 ** out_decimals))
        else:
            min_dy = int(dy * (1 - self.slippage / 100))

        amount_out = dy / (10 ** out_decimals)

        # Approve token_in for the pool
        self._approve_token(wallet, w3, chain, token_in, pool, amount_wei)

        tx = pool_contract.functions.exchange(i, j, amount_wei, min_dy).build_transaction({})

        result = self._build_and_send(wallet, w3, chain, tx)

        return SwapResult(
            tx_hash=result["tx_hash"],
            token_in=token_in,
            token_out=token_out,
            amount_in=amount,
            amount_out=amount_out,
            gas_used=result["gas_used"],
            chain=chain,
        )

    def get_swap_estimate(self, pool: str, token_in: str, token_out: str,
                          amount: float, chain: Chain = Chain.ETHEREUM) -> dict:
        """Get a swap quote from a Curve pool without executing.

        Args:
            pool: Curve pool address
            token_in: Input token address
            token_out: Output token address
            amount: Amount in human-readable units
            chain: Chain to query

        Returns:
            Dict with amount_out, price, pool info
        """
        if chain not in self.supported_chains:
            raise ValueError(f"Curve not supported on {chain.value}")
        if not self.chain_manager:
            raise ValueError("ChainManager required for Curve quotes")

        try:
            w3, pool_contract = self._get_pool_contract(pool, chain)
            i = self._find_coin_index(pool_contract, token_in, w3)
            j = self._find_coin_index(pool_contract, token_out, w3)

            in_decimals = self._get_token_decimals(w3, token_in)
            out_decimals = self._get_token_decimals(w3, token_out)
            amount_wei = int(amount * (10 ** in_decimals))

            dy = pool_contract.functions.get_dy(i, j, amount_wei).call()
            amount_out = dy / (10 ** out_decimals)
            price = amount_out / amount if amount > 0 else 0

            fee = pool_contract.functions.fee().call()

            return {
                "amount_in": amount,
                "amount_out": round(amount_out, 8),
                "price": round(price, 8),
                "fee": fee / 10**10,  # Curve fee is in 1e10 scale
                "pool": pool,
                "chain": chain.value,
            }
        except (ConnectionError, OSError, ValueError) as e:
            logger.warning(f"Curve quote failed: {e}")
            return {"error": str(e), "pool": pool, "chain": chain.value}

    def get_pool_info(self, pool_address: str, chain: Chain = Chain.ETHEREUM) -> CurvePoolInfo:
        """Get Curve pool information.

        Args:
            pool_address: Pool contract address
            chain: Chain to query

        Returns:
            CurvePoolInfo with tokens, balances, fee, A parameter
        """
        if chain not in self.supported_chains:
            raise ValueError(f"Curve not supported on {chain.value}")

        try:
            if not self.chain_manager:
                raise ValueError("ChainManager required for Curve queries")
            w3 = self.chain_manager.get_web3(chain)
            addr = w3.to_checksum_address(pool_address)
            pool = w3.eth.contract(address=addr, abi=CURVE_POOL_ABI)

            coins: list[str] = []
            balances: list[float] = []

            # Try get_coins/get_balances first (works for most pools)
            try:
                raw_coins = pool.functions.get_coins().call()
                raw_balances = pool.functions.get_balances().call()
                for idx, c in enumerate(raw_coins):
                    if c == "0x0000000000000000000000000000000000000000":
                        break
                    coins.append(c)
                    decimals = self._get_token_decimals(w3, c)
                    balances.append(raw_balances[idx] / (10 ** decimals))
            except Exception:
                # Fallback to coins(i)/balances(i)
                for i in range(8):
                    try:
                        c = pool.functions.coins(i).call()
                        if c == "0x0000000000000000000000000000000000000000":
                            break
                        coins.append(c)
                        b = pool.functions.balances(i).call()
                        decimals = self._get_token_decimals(w3, c)
                        balances.append(b / (10 ** decimals))
                    except Exception:
                        break

            try:
                fee = pool.functions.fee().call() / 10**10
            except Exception:
                fee = 0.0004  # default 0.04%

            try:
                a = pool.functions.A().call()
            except Exception:
                a = 0

            try:
                total_supply = pool.functions.totalSupply().call() / 10**18
            except Exception:
                total_supply = 0.0

            return CurvePoolInfo(
                pool_address=addr,
                coins=coins,
                balances=balances,
                fee=fee,
                A=a,
                total_supply=total_supply,
            )
        except (ConnectionError, OSError, ValueError) as e:
            logger.warning(f"Failed to fetch Curve pool info for {pool_address}: {e}")
            return CurvePoolInfo(
                pool_address=pool_address,
                coins=[],
                balances=[],
                fee=0.0004,
                A=0,
                total_supply=0.0,
            )

    def add_liquidity(self, wallet: Wallet, pool: str, amounts: list[float],
                      chain: Chain = Chain.ETHEREUM, **kwargs) -> dict:
        """Add liquidity to a Curve pool.

        Args:
            wallet: Wallet providing liquidity
            pool: Curve pool address
            amounts: List of token amounts in human-readable units (must match pool coin order)
            chain: Chain to operate on

        Returns:
            Dict with tx_hash, gas_used
        """
        w3, pool_contract = self._get_pool_contract(pool, chain)

        # Get pool coins to determine decimals
        try:
            raw_coins = pool_contract.functions.get_coins().call()
        except Exception:
            raw_coins = []
            for i in range(8):
                try:
                    c = pool_contract.functions.coins(i).call()
                    if c == "0x0000000000000000000000000000000000000000":
                        break
                    raw_coins.append(c)
                except Exception:
                    break

        if len(amounts) != len(raw_coins):
            raise ValueError(
                f"Expected {len(raw_coins)} amounts (one per pool coin), got {len(amounts)}"
            )

        # Convert to wei
        wei_amounts = []
        for idx, amt in enumerate(amounts):
            decimals = self._get_token_decimals(w3, raw_coins[idx])
            wei_amounts.append(int(amt * (10 ** decimals)))

            # Approve each token for the pool
            if amt > 0:
                self._approve_token(
                    wallet, w3, chain, raw_coins[idx], pool,
                    int(amt * (10 ** decimals))
                )

        min_mint = 0  # Accept any LP tokens (slippage handled off-chain)

        if len(wei_amounts) == 2:
            tx = pool_contract.functions.add_liquidity(
                wei_amounts[:2], min_mint
            ).build_transaction({})
        elif len(wei_amounts) <= 4:
            padded = wei_amounts + [0] * (4 - len(wei_amounts))
            tx = pool_contract.functions.add_liquidity(
                padded[:4], min_mint
            ).build_transaction({})
        else:
            raise ValueError("Pools with >4 coins not supported in this integration")

        return self._build_and_send(wallet, w3, chain, tx)

    def remove_liquidity(self, wallet: Wallet, pool: str, amount: float,
                         chain: Chain = Chain.ETHEREUM, **kwargs) -> dict:
        """Remove liquidity from a Curve pool (proportional withdrawal).

        Args:
            wallet: Wallet removing liquidity
            pool: Curve pool address
            amount: Amount of LP tokens to redeem (in human-readable units)
            chain: Chain to operate on

        Returns:
            Dict with tx_hash, gas_used
        """
        w3, pool_contract = self._get_pool_contract(pool, chain)
        amount_wei = int(amount * 10**18)  # LP tokens are 18 decimals

        # Determine pool size
        try:
            raw_coins = pool_contract.functions.get_coins().call()
            n_coins = len([c for c in raw_coins if c != "0x0000000000000000000000000000000000000000"])
        except Exception:
            n_coins = 2  # default

        min_amounts = [0] * n_coins

        if n_coins == 2:
            tx = pool_contract.functions.remove_liquidity(
                amount_wei, min_amounts[:2]
            ).build_transaction({})
        elif n_coins <= 4:
            padded = min_amounts + [0] * (4 - len(min_amounts))
            tx = pool_contract.functions.remove_liquidity(
                amount_wei, padded[:4]
            ).build_transaction({})
        else:
            raise ValueError("Pools with >4 coins not supported")

        return self._build_and_send(wallet, w3, chain, tx)

    def _approve_token(self, wallet: Wallet, w3, chain: Chain, token_addr: str,
                       spender: str, amount: int) -> None:
        """Approve a token for Curve pool spending."""
        token = w3.eth.contract(address=w3.to_checksum_address(token_addr), abi=ERC20_ABI)
        allowance = token.functions.allowance(
            w3.to_checksum_address(wallet.address),
            w3.to_checksum_address(spender)
        ).call()
        if allowance >= amount:
            logger.info(f"Token already approved ({allowance} >= {amount})")
            return

        approve_tx = token.functions.approve(
            w3.to_checksum_address(spender), 2**256 - 1
        ).build_transaction({
            "from": w3.to_checksum_address(wallet.address),
            "gas": 100000,
            "gasPrice": w3.eth.gas_price,
            "nonce": w3.eth.get_transaction_count(wallet.address),
            "chainId": CHAIN_IDS.get(chain, 1),
        })
        signed = wallet.sign_transaction(approve_tx, chain)
        tx_hash = w3.eth.send_raw_transaction(signed)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
        logger.info(f"Token approved for Curve: {tx_hash.hex()} (gas: {receipt.gasUsed})")

__all__ = [
    # Swap
    "SwapResult",
    "Uniswap",
    "UniswapV3",
    "V3SwapResult",
    "PoolInfo",
    "PositionInfo",
    "Aerodrome",
    "Aave",
    "Curve",
    "DeFiTool",
    "YieldOpportunity",
    # Aave
    "AaveUserData",
    "AaveReserveData",
    "AAVE_POOL_ABI",
    "AAVE_RATE_MODE_VARIABLE",
    "AAVE_RATE_MODE_STABLE",
    # Curve
    "CurvePoolInfo",
    "CURVE_POOL_ABI",
    # Yield Optimizer
    "YieldOptimizer",
    "YieldConfig",
    "YieldPosition",
    "YieldProtocol",
    "YieldRiskLevel",
    # Constants
    "WETH",
    "NATIVE",
    "STABLECOINS",
    "UNISWAP_V2_ROUTER_ABI",
    "ERC20_ABI",
    # V3
    "FEE_TIERS",
    "SWAP_ROUTER",
    "SWAP_ROUTER_02",
    "QUOTER_V2",
    "NONFUNGIBLE_POSITION_MANAGER",
    "FACTORY",
]
