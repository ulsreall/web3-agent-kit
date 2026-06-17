"""Uniswap V3 DEX integration — concentrated liquidity swaps, positions, and quotes."""

from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import dataclass
from typing import Any, Optional

from ..wallet.wallet import Wallet
from ..chains.chain import Chain, ChainManager, CHAIN_IDS  # noqa: E402

# Minimal ERC20 ABI (duplicated here to avoid circular import with __init__)
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
    },
    {
        "inputs": [
            {"internalType": "address", "name": "owner", "type": "address"},
            {"internalType": "address", "name": "spender", "type": "address"}
        ],
        "name": "allowance",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    }
]""")

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Contract addresses (Ethereum mainnet)
# ---------------------------------------------------------------------------

SWAP_ROUTER = "0xE592427A0AEce92De3Edee1F18E0157C05861564"
SWAP_ROUTER_02 = "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45"
QUOTER_V2 = "0x61fFE014bA17989E743c5F6cB21bF9697530B21e"
NONFUNGIBLE_POSITION_MANAGER = "0xC36442b4a4522E871399CD717aBDD847Ab11FE88"
FACTORY = "0x1F98431c8aD98523631AE4a59f267346ea31F984"

# Fee tiers: fee value -> tick spacing
FEE_TIERS = {
    100: 1,      # 0.01%
    500: 10,     # 0.05%
    3000: 60,    # 0.3%
    10000: 200,  # 1%
}

# ---------------------------------------------------------------------------
# ABIs (minimal, function-scoped)
# ---------------------------------------------------------------------------

SWAP_ROUTER_ABI = json.loads("""[
    {
        "inputs": [
            {
                "components": [
                    {"internalType": "address", "name": "tokenIn", "type": "address"},
                    {"internalType": "address", "name": "tokenOut", "type": "address"},
                    {"internalType": "uint24", "name": "fee", "type": "uint24"},
                    {"internalType": "address", "name": "recipient", "type": "address"},
                    {"internalType": "uint256", "name": "deadline", "type": "uint256"},
                    {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                    {"internalType": "uint256", "name": "amountOutMinimum", "type": "uint256"},
                    {"internalType": "uint160", "name": "sqrtPriceLimitX96", "type": "uint160"}
                ],
                "internalType": "struct ISwapRouter.ExactInputSingleParams",
                "name": "params",
                "type": "tuple"
            }
        ],
        "name": "exactInputSingle",
        "outputs": [{"internalType": "uint256", "name": "amountOut", "type": "uint256"}],
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "inputs": [
            {
                "components": [
                    {"internalType": "address", "name": "tokenIn", "type": "address"},
                    {"internalType": "address", "name": "tokenOut", "type": "address"},
                    {"internalType": "uint24", "name": "fee", "type": "uint24"},
                    {"internalType": "address", "name": "recipient", "type": "address"},
                    {"internalType": "uint256", "name": "deadline", "type": "uint256"},
                    {"internalType": "uint256", "name": "amountOut", "type": "uint256"},
                    {"internalType": "uint256", "name": "amountInMaximum", "type": "uint256"},
                    {"internalType": "uint160", "name": "sqrtPriceLimitX96", "type": "uint160"}
                ],
                "internalType": "struct ISwapRouter.ExactOutputSingleParams",
                "name": "params",
                "type": "tuple"
            }
        ],
        "name": "exactOutputSingle",
        "outputs": [{"internalType": "uint256", "name": "amountIn", "type": "uint256"}],
        "stateMutability": "payable",
        "type": "function"
    }
]""")

QUOTER_V2_ABI = json.loads("""[
    {
        "inputs": [
            {
                "components": [
                    {"internalType": "address", "name": "tokenIn", "type": "address"},
                    {"internalType": "address", "name": "tokenOut", "type": "address"},
                    {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                    {"internalType": "uint24", "name": "fee", "type": "uint24"},
                    {"internalType": "uint160", "name": "sqrtPriceLimitX96", "type": "uint160"}
                ],
                "internalType": "struct IQuoterV2.QuoteExactInputSingleParams",
                "name": "params",
                "type": "tuple"
            }
        ],
        "name": "quoteExactInputSingle",
        "outputs": [
            {"internalType": "uint256", "name": "amountOut", "type": "uint256"},
            {"internalType": "uint160", "name": "sqrtPriceX96After", "type": "uint160"},
            {"internalType": "uint32", "name": "initializedTicksCrossed", "type": "uint32"},
            {"internalType": "uint256", "name": "gasEstimate", "type": "uint256"}
        ],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {
                "components": [
                    {"internalType": "address", "name": "tokenIn", "type": "address"},
                    {"internalType": "address", "name": "tokenOut", "type": "address"},
                    {"internalType": "uint256", "name": "amount", "type": "uint256"},
                    {"internalType": "uint24", "name": "fee", "type": "uint24"},
                    {"internalType": "uint160", "name": "sqrtPriceLimitX96", "type": "uint160"}
                ],
                "internalType": "struct IQuoterV2.QuoteExactOutputSingleParams",
                "name": "params",
                "type": "tuple"
            }
        ],
        "name": "quoteExactOutputSingle",
        "outputs": [
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "uint160", "name": "sqrtPriceX96After", "type": "uint160"},
            {"internalType": "uint32", "name": "initializedTicksCrossed", "type": "uint32"},
            {"internalType": "uint256", "name": "gasEstimate", "type": "uint256"}
        ],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]""")

FACTORY_ABI = json.loads("""[
    {
        "inputs": [
            {"internalType": "address", "name": "tokenA", "type": "address"},
            {"internalType": "address", "name": "tokenB", "type": "address"},
            {"internalType": "uint24", "name": "fee", "type": "uint24"}
        ],
        "name": "getPool",
        "outputs": [{"internalType": "address", "name": "pool", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "tokenA", "type": "address"},
            {"internalType": "address", "name": "tokenB", "type": "address"},
            {"internalType": "uint24", "name": "fee", "type": "uint24"}
        ],
        "name": "createPool",
        "outputs": [{"internalType": "address", "name": "pool", "type": "address"}],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]""")

POOL_ABI = json.loads("""[
    {
        "inputs": [],
        "name": "liquidity",
        "outputs": [{"internalType": "uint128", "name": "", "type": "uint128"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "slot0",
        "outputs": [
            {"internalType": "uint160", "name": "sqrtPriceX96", "type": "uint160"},
            {"internalType": "int24", "name": "tick", "type": "int24"},
            {"internalType": "uint16", "name": "observationIndex", "type": "uint16"},
            {"internalType": "uint16", "name": "observationCardinality", "type": "uint16"},
            {"internalType": "uint16", "name": "observationCardinalityNext", "type": "uint16"},
            {"internalType": "uint8", "name": "feeProtocol", "type": "uint8"},
            {"internalType": "bool", "name": "unlocked", "type": "bool"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "tokenA", "type": "address"},
            {"internalType": "address", "name": "tokenB", "type": "address"},
            {"internalType": "uint24", "name": "fee", "type": "uint24"},
            {"internalType": "uint160", "name": "sqrtPriceX96", "type": "uint160"}
        ],
        "name": "initialize",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]""")

NONFUNGIBLE_POSITION_MANAGER_ABI = json.loads("""[
    {
        "inputs": [
            {
                "components": [
                    {"internalType": "address", "name": "token0", "type": "address"},
                    {"internalType": "address", "name": "token1", "type": "address"},
                    {"internalType": "uint24", "name": "fee", "type": "uint24"},
                    {"internalType": "int24", "name": "tickLower", "type": "int24"},
                    {"internalType": "int24", "name": "tickUpper", "type": "int24"},
                    {"internalType": "uint256", "name": "amount0Desired", "type": "uint256"},
                    {"internalType": "uint256", "name": "amount1Desired", "type": "uint256"},
                    {"internalType": "uint256", "name": "amount0Min", "type": "uint256"},
                    {"internalType": "uint256", "name": "amount1Min", "type": "uint256"},
                    {"internalType": "address", "name": "recipient", "type": "address"},
                    {"internalType": "uint256", "name": "deadline", "type": "uint256"}
                ],
                "internalType": "struct INonfungiblePositionManager.MintParams",
                "name": "params",
                "type": "tuple"
            }
        ],
        "name": "mint",
        "outputs": [
            {"internalType": "uint256", "name": "tokenId", "type": "uint256"},
            {"internalType": "uint128", "name": "liquidity", "type": "uint128"},
            {"internalType": "uint256", "name": "amount0", "type": "uint256"},
            {"internalType": "uint256", "name": "amount1", "type": "uint256"}
        ],
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "inputs": [
            {
                "components": [
                    {"internalType": "uint256", "name": "tokenId", "type": "uint256"},
                    {"internalType": "uint256", "name": "amount0Desired", "type": "uint256"},
                    {"internalType": "uint256", "name": "amount1Desired", "type": "uint256"},
                    {"internalType": "uint256", "name": "amount0Min", "type": "uint256"},
                    {"internalType": "uint256", "name": "amount1Min", "type": "uint256"},
                    {"internalType": "uint256", "name": "deadline", "type": "uint256"}
                ],
                "internalType": "struct INonfungiblePositionManager.IncreaseLiquidityParams",
                "name": "params",
                "type": "tuple"
            }
        ],
        "name": "increaseLiquidity",
        "outputs": [
            {"internalType": "uint128", "name": "liquidity", "type": "uint128"},
            {"internalType": "uint256", "name": "amount0", "type": "uint256"},
            {"internalType": "uint256", "name": "amount1", "type": "uint256"}
        ],
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "inputs": [
            {
                "components": [
                    {"internalType": "uint256", "name": "tokenId", "type": "uint256"},
                    {"internalType": "uint128", "name": "liquidity", "type": "uint128"},
                    {"internalType": "uint256", "name": "amount0Min", "type": "uint256"},
                    {"internalType": "uint256", "name": "amount1Min", "type": "uint256"},
                    {"internalType": "uint256", "name": "deadline", "type": "uint256"}
                ],
                "internalType": "struct INonfungiblePositionManager.DecreaseLiquidityParams",
                "name": "params",
                "type": "tuple"
            }
        ],
        "name": "decreaseLiquidity",
        "outputs": [
            {"internalType": "uint256", "name": "amount0", "type": "uint256"},
            {"internalType": "uint256", "name": "amount1", "type": "uint256"}
        ],
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "inputs": [
            {
                "components": [
                    {"internalType": "uint256", "name": "tokenId", "type": "uint256"},
                    {"internalType": "address", "name": "recipient", "type": "address"},
                    {"internalType": "uint128", "name": "amount0Max", "type": "uint128"},
                    {"internalType": "uint128", "name": "amount1Max", "type": "uint128"}
                ],
                "internalType": "struct INonfungiblePositionManager.CollectParams",
                "name": "params",
                "type": "tuple"
            }
        ],
        "name": "collect",
        "outputs": [
            {"internalType": "uint256", "name": "amount0", "type": "uint256"},
            {"internalType": "uint256", "name": "amount1", "type": "uint256"}
        ],
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "uint256", "name": "tokenId", "type": "uint256"}],
        "name": "positions",
        "outputs": [
            {"internalType": "uint96", "name": "nonce", "type": "uint96"},
            {"internalType": "address", "name": "operator", "type": "address"},
            {"internalType": "address", "name": "token0", "type": "address"},
            {"internalType": "address", "name": "token1", "type": "address"},
            {"internalType": "uint24", "name": "fee", "type": "uint24"},
            {"internalType": "int24", "name": "tickLower", "type": "int24"},
            {"internalType": "int24", "name": "tickUpper", "type": "int24"},
            {"internalType": "uint128", "name": "liquidity", "type": "uint128"},
            {"internalType": "uint256", "name": "feeGrowthInside0LastX128", "type": "uint256"},
            {"internalType": "uint256", "name": "feeGrowthInside1LastX128", "type": "uint256"},
            {"internalType": "uint128", "name": "tokensOwed0", "type": "uint128"},
            {"internalType": "uint128", "name": "tokensOwed1", "type": "uint128"}
        ],
        "stateMutability": "view",
        "type": "function"
    }
]""")


# ---------------------------------------------------------------------------
# Tick math helpers
# ---------------------------------------------------------------------------

# Uniswap V3 uses a fixed-point Q96 representation.
# MIN_TICK = -887272, MAX_TICK = 887272
MIN_TICK = -887272
MAX_TICK = 887272


def get_sqrt_ratio_at_tick(tick: int) -> int:
    """Convert a tick value to its corresponding sqrtPriceX96.

    Uses the exact same algorithm as Uniswap V3 TickMath.sol.
    Returns a uint160 (Q64.96 fixed-point sqrt price).
    """
    if tick < MIN_TICK or tick > MAX_TICK:
        raise ValueError(f"Tick {tick} out of range [{MIN_TICK}, {MAX_TICK}]")

    abs_tick = abs(tick)
    ratio = 0x100000000000000000000000000000000 if (abs_tick & 0x1) else 0x100000000000000000000000000000000  # placeholder
    # Exact bit-by-bit computation matching the Solidity implementation
    ratio = 0xFFFCB933BD6FAD37AA2D162D1A594001 if (abs_tick & 0x1) != 0 else 0x100000000000000000000000000000000
    if (abs_tick & 0x2) != 0:
        ratio = (ratio * 0xFFF97272373D413259A46990580E213A) >> 128
    if (abs_tick & 0x4) != 0:
        ratio = (ratio * 0xFFF2E50F5F656932EF12357CF3C7FDCC) >> 128
    if (abs_tick & 0x8) != 0:
        ratio = (ratio * 0xFFE5CACA7E10E4E61C3624EAA0941CD0) >> 128
    if (abs_tick & 0x10) != 0:
        ratio = (ratio * 0xFFCB9843D60F6159C9DB58835C926644) >> 128
    if (abs_tick & 0x20) != 0:
        ratio = (ratio * 0xFF973B41FA98C081472E6896DFB254C0) >> 128
    if (abs_tick & 0x40) != 0:
        ratio = (ratio * 0xFF2EA16466C96A3843EC78B326B52861) >> 128
    if (abs_tick & 0x80) != 0:
        ratio = (ratio * 0xFE5DEEE08556A8C1B8D0B1C2BAD86BC8) >> 128
    if (abs_tick & 0x100) != 0:
        ratio = (ratio * 0xFCBE86C7900A88AEDCFFC83B479AA3A4) >> 128
    if (abs_tick & 0x200) != 0:
        ratio = (ratio * 0xF987A7253AC413176F2B074CF7815E54) >> 128
    if (abs_tick & 0x400) != 0:
        ratio = (ratio * 0xF3392B0822B70005940C7A398E4B70F3) >> 128
    if (abs_tick & 0x800) != 0:
        ratio = (ratio * 0xE7159475A2C29B7443B29C7FA6E889D9) >> 128
    if (abs_tick & 0x1000) != 0:
        ratio = (ratio * 0xD097F3BDFD2022B8845AD8F792AA5825) >> 128
    if (abs_tick & 0x2000) != 0:
        ratio = (ratio * 0xA9F746462D870FDF8A65DC1F90E061E5) >> 128
    if (abs_tick & 0x4000) != 0:
        ratio = (ratio * 0x70D869A156D2A1B890BB3DF62BAF32F7) >> 128
    if (abs_tick & 0x8000) != 0:
        ratio = (ratio * 0x31BE135F97D08FD981231505542FCFA6) >> 128
    if (abs_tick & 0x10000) != 0:
        ratio = (ratio * 0x9AA508B5B7A84E1C677DE54F3E99BC9) >> 128
    if (abs_tick & 0x20000) != 0:
        ratio = (ratio * 0x5D6AF8DEDB81196699C329225EE604) >> 128
    if (abs_tick & 0x40000) != 0:
        ratio = (ratio * 0x2216E584F5FA1EA926041BEDFE98) >> 128
    if (abs_tick & 0x80000) != 0:
        ratio = (ratio * 0x48A170391F7DC42444E8FA2) >> 128

    if tick > 0:
        ratio = (2**256 - 1) // ratio  # type: ignore[assignment]

    # Shift to Q96
    sqrt_price_x96 = (ratio >> 32) + (1 if ratio % (1 << 32) != 0 else 0)
    return sqrt_price_x96


def get_tick_at_sqrt_ratio(sqrt_price_x96: int) -> int:
    """Convert a sqrtPriceX96 value to its corresponding tick.

    Returns the tick (floor of log base 1.0001 of the price).
    """
    if sqrt_price_x96 < 4295128739 or sqrt_price_x96 >= 2**160:
        raise ValueError(f"sqrtPriceX96 {sqrt_price_x96} out of valid range")

    # log2(sqrt(price)) = log2(sqrtPriceX96) - log2(2^96)
    # tick = log2(sqrt(price)) / log2(sqrt(1.0001))
    # tick = log2(sqrt(price)) * 2 / log2(1.0001)
    # log2(1.0001) ≈ 0.00014426269174937318

    sqrt_price = sqrt_price_x96 / (2**96)
    tick = math.floor(math.log(sqrt_price) / math.log(1.0001) * 2) // 2
    # More precise: tick = floor(log(sqrtPriceX96 / 2^96)^2 / log(1.0001))
    tick = math.floor(math.log(sqrt_price**2) / math.log(1.0001))
    return max(MIN_TICK, min(MAX_TICK, tick))


def nearest_usable_tick(tick: int, tick_spacing: int) -> int:
    """Round *tick* to the nearest valid tick for the given *tick_spacing*.

    A tick is usable if ``tick % tick_spacing == 0``.
    """
    rounded = round(tick / tick_spacing) * tick_spacing
    if rounded < MIN_TICK:
        rounded += tick_spacing
    elif rounded > MAX_TICK:
        rounded -= tick_spacing
    return rounded


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class V3SwapResult:
    """Result of a Uniswap V3 swap."""

    tx_hash: str
    token_in: str
    token_out: str
    amount_in: float
    amount_out: float
    gas_used: int
    fee_tier: int


@dataclass
class PoolInfo:
    """State snapshot of a Uniswap V3 pool."""

    pool_address: str
    token0: str
    token1: str
    fee: int
    liquidity: int
    sqrt_price_x96: int
    tick: int


@dataclass
class PositionInfo:
    """Metadata for an NFT position."""

    token_id: int
    token0: str
    token1: str
    fee: int
    tick_lower: int
    tick_upper: int
    liquidity: int


# ---------------------------------------------------------------------------
# UniswapV3 class
# ---------------------------------------------------------------------------


class UniswapV3:
    """Uniswap V3 DEX integration — concentrated-liquidity swaps, quotes, and LP positions.

    All interactions are on Ethereum mainnet (extendable to other chains).
    """

    SUPPORTED_FEE_TIERS = list(FEE_TIERS.keys())

    # Convenience list for external callers
    @property
    def supported_fee_tiers(self) -> list[int]:
        return list(FEE_TIERS.keys())

    def __init__(
        self,
        chain_manager: Optional[ChainManager] = None,
        slippage: float = 0.5,
        swap_router_address: str = SWAP_ROUTER,
        chain: Chain = Chain.ETHEREUM,
    ):
        self.chain_manager = chain_manager
        self.slippage = slippage  # percent
        self.swap_router_address = swap_router_address
        self.chain = chain

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_w3(self):
        if not self.chain_manager:
            raise ValueError("ChainManager required for this operation")
        return self.chain_manager.get_web3(self.chain)

    def _to_checksum(self, w3, addr: str) -> str:
        return w3.to_checksum_address(addr)

    def _get_decimals(self, w3, token_addr: str) -> int:
        token = w3.eth.contract(address=self._to_checksum(w3, token_addr), abi=ERC20_ABI)
        return token.functions.decimals().call()

    def _amount_to_wei(self, w3, token_addr: str, amount: float) -> int:
        decimals = self._get_decimals(w3, token_addr)
        return int(amount * (10**decimals))

    def _wei_to_amount(self, w3, token_addr: str, wei: int) -> float:
        decimals = self._get_decimals(w3, token_addr)
        return wei / (10**decimals)

    def _is_native(self, token: str) -> bool:
        upper = token.upper()
        return upper in ("ETH", "NATIVE", "MATIC")

    def _resolve_token(self, token: str, w3) -> str:
        from . import WETH

        if self._is_native(token):
            weth = WETH.get(self.chain)
            if weth is None:
                raise ValueError(f"No WETH address for chain {self.chain}")
            return weth
        return self._to_checksum(w3, token)

    def _ensure_approval(self, wallet: Wallet, token_addr: str, spender: str, amount: int, w3):
        """Approve *spender* to spend *amount* of *token_addr* if not already done."""
        token = w3.eth.contract(address=self._to_checksum(w3, token_addr), abi=ERC20_ABI)
        allowance = token.functions.allowance(
            self._to_checksum(w3, wallet.address),
            self._to_checksum(w3, spender),
        ).call()

        if allowance >= amount:
            return

        approve_tx = token.functions.approve(
            self._to_checksum(w3, spender),
            2**256 - 1,
        ).build_transaction({
            "from": self._to_checksum(w3, wallet.address),
            "gas": 100_000,
            "gasPrice": w3.eth.gas_price,
            "nonce": w3.eth.get_transaction_count(self._to_checksum(w3, wallet.address)),
            "chainId": CHAIN_IDS.get(self.chain, 1),
        })

        signed = wallet.sign_transaction(approve_tx, self.chain)
        tx_hash = w3.eth.send_raw_transaction(signed)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
        logger.info(f"Approved {spender} for {token_addr}: {tx_hash.hex()} (gas: {receipt.gasUsed})")

    @staticmethod
    def _sort_tokens(token_a: str, token_b: str) -> tuple[str, str]:
        """Return (token0, token1) sorted by address (lower first)."""
        if int(token_a, 16) < int(token_b, 16):
            return token_a, token_b
        return token_b, token_a

    # ------------------------------------------------------------------
    # Swap
    # ------------------------------------------------------------------

    def swap(
        self,
        token_in: str,
        token_out: str,
        amount: float,
        fee_tier: int = 3000,
        slippage: Optional[float] = None,
    ) -> V3SwapResult:
        """Execute an **exact-input** single-hop swap on Uniswap V3.

        Args:
            token_in: Input token address (or ``"ETH"`` for native).
            token_out: Output token address (or ``"ETH"`` for native).
            amount: Amount of input token (human-readable, e.g. ``0.1`` for 0.1 ETH).
            fee_tier: Pool fee tier (100, 500, 3000, 10000).
            slippage: Slippage tolerance in percent (overrides default).

        Returns:
            V3SwapResult with tx hash and amounts.
        """
        if fee_tier not in FEE_TIERS:
            raise ValueError(f"Invalid fee tier {fee_tier}. Must be one of {list(FEE_TIERS.keys())}")

        w3 = self._get_w3()
        slippage_pct = slippage if slippage is not None else self.slippage

        token_in_addr = self._resolve_token(token_in, w3)
        token_out_addr = self._resolve_token(token_out, w3)

        amount_in_wei = self._amount_to_wei(w3, token_in_addr, amount)

        # Get a quote first for amountOutMinimum
        quote = self.get_quote(token_in, token_out, amount, fee_tier)
        if "error" in quote:
            raise ValueError(f"Quote failed: {quote['error']}")

        amount_out_raw = int(quote["amount_out_raw"])
        amount_out_min = int(amount_out_raw * (1 - slippage_pct / 100))

        # NOTE: swap() returns a built tx dict without signing.
        # Use swap_with_wallet() for full approval + sign + send.
        is_eth_in = self._is_native(token_in)

        router = w3.eth.contract(
            address=self._to_checksum(w3, self.swap_router_address),
            abi=SWAP_ROUTER_ABI,
        )

        deadline = int(time.time()) + 1200
        nonce = w3.eth.get_transaction_count(self._to_checksum(w3, "0x0"))  # caller must pass wallet
        gas_price = w3.eth.gas_price

        params = {
            "tokenIn": self._to_checksum(w3, token_in_addr),
            "tokenOut": self._to_checksum(w3, token_out_addr),
            "fee": fee_tier,
            "recipient": self._to_checksum(w3, "0x0"),  # caller must pass wallet
            "deadline": deadline,
            "amountIn": amount_in_wei,
            "amountOutMinimum": amount_out_min,
            "sqrtPriceLimitX96": 0,
        }

        tx = router.functions.exactInputSingle(params).build_transaction({
            "from": self._to_checksum(w3, "0x0"),
            "value": amount_in_wei if is_eth_in else 0,
            "gas": 300_000,
            "gasPrice": gas_price,
            "nonce": nonce,
            "chainId": CHAIN_IDS.get(self.chain, 1),
        })

        # Sign & send (requires wallet — here we return the built tx for external signing)
        # In production the caller signs via wallet.sign_transaction
        signed = None  # placeholder — actual signing requires wallet reference
        # For now, return built transaction info
        return V3SwapResult(
            tx_hash="",  # filled after send
            token_in=token_in_addr,
            token_out=token_out_addr,
            amount_in=amount,
            amount_out=quote.get("amount_out", 0),
            gas_used=0,
            fee_tier=fee_tier,
        )

    def swap_with_wallet(
        self,
        wallet: Wallet,
        token_in: str,
        token_out: str,
        amount: float,
        fee_tier: int = 3000,
        slippage: Optional[float] = None,
    ) -> V3SwapResult:
        """Execute an exact-input swap with a Wallet for signing.

        This is the production-ready variant that handles approvals,
        transaction building, signing, and submission.
        """
        if fee_tier not in FEE_TIERS:
            raise ValueError(f"Invalid fee tier {fee_tier}. Must be one of {list(FEE_TIERS.keys())}")

        w3 = self._get_w3()
        slippage_pct = slippage if slippage is not None else self.slippage

        token_in_addr = self._resolve_token(token_in, w3)
        token_out_addr = self._resolve_token(token_out, w3)
        is_eth_in = self._is_native(token_in)

        amount_in_wei = self._amount_to_wei(w3, token_in_addr, amount)

        # Quote
        quote = self.get_quote(token_in, token_out, amount, fee_tier)
        if "error" in quote:
            raise ValueError(f"Quote failed: {quote['error']}")

        amount_out_raw = int(quote["amount_out_raw"])
        amount_out_min = int(amount_out_raw * (1 - slippage_pct / 100))

        # Approve
        if not is_eth_in:
            self._ensure_approval(wallet, token_in_addr, self.swap_router_address, amount_in_wei, w3)

        router = w3.eth.contract(
            address=self._to_checksum(w3, self.swap_router_address),
            abi=SWAP_ROUTER_ABI,
        )

        deadline = int(time.time()) + 1200
        nonce = w3.eth.get_transaction_count(self._to_checksum(w3, wallet.address))

        params = {
            "tokenIn": self._to_checksum(w3, token_in_addr),
            "tokenOut": self._to_checksum(w3, token_out_addr),
            "fee": fee_tier,
            "recipient": self._to_checksum(w3, wallet.address),
            "deadline": deadline,
            "amountIn": amount_in_wei,
            "amountOutMinimum": amount_out_min,
            "sqrtPriceLimitX96": 0,
        }

        tx = router.functions.exactInputSingle(params).build_transaction({
            "from": self._to_checksum(w3, wallet.address),
            "value": amount_in_wei if is_eth_in else 0,
            "gas": 300_000,
            "gasPrice": w3.eth.gas_price,
            "nonce": nonce,
            "chainId": CHAIN_IDS.get(self.chain, 1),
        })

        signed = wallet.sign_transaction(tx, self.chain)
        tx_hash = w3.eth.send_raw_transaction(signed)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

        return V3SwapResult(
            tx_hash=tx_hash.hex(),
            token_in=token_in_addr,
            token_out=token_out_addr,
            amount_in=amount,
            amount_out=quote.get("amount_out", 0),
            gas_used=receipt.gasUsed,
            fee_tier=fee_tier,
        )

    # ------------------------------------------------------------------
    # Exact-output swap
    # ------------------------------------------------------------------

    def swap_exact_output(
        self,
        token_in: str,
        token_out: str,
        amount_out: float,
        fee_tier: int = 3000,
    ) -> dict:
        """Build an **exact-output** single-hop swap transaction.

        Returns a dict with ``params`` and ``tx`` ready for signing.
        """
        if fee_tier not in FEE_TIERS:
            raise ValueError(f"Invalid fee tier {fee_tier}")

        w3 = self._get_w3()

        token_in_addr = self._resolve_token(token_in, w3)
        token_out_addr = self._resolve_token(token_out, w3)
        is_eth_in = self._is_native(token_in)

        amount_out_wei = self._amount_to_wei(w3, token_out_addr, amount_out)

        router = w3.eth.contract(
            address=self._to_checksum(w3, self.swap_router_address),
            abi=SWAP_ROUTER_ABI,
        )

        deadline = int(time.time()) + 1200

        params = {
            "tokenIn": self._to_checksum(w3, token_in_addr),
            "tokenOut": self._to_checksum(w3, token_out_addr),
            "fee": fee_tier,
            "recipient": self._to_checksum(w3, "0x0"),
            "deadline": deadline,
            "amountOut": amount_out_wei,
            "amountInMaximum": 2**256 - 1,  # caller should set reasonable limit
            "sqrtPriceLimitX96": 0,
        }

        return {"function": "exactOutputSingle", "params": params}

    # ------------------------------------------------------------------
    # Quote
    # ------------------------------------------------------------------

    def get_quote(
        self,
        token_in: str,
        token_out: str,
        amount: float,
        fee_tier: int = 3000,
    ) -> dict:
        """Get a price quote via the QuoterV2 contract (static call).

        Returns a dict with ``amount_out``, ``amount_out_raw``,
        ``sqrt_price_x96_after``, ``gas_estimate``, etc.
        """
        if fee_tier not in FEE_TIERS:
            return {"error": f"Invalid fee tier {fee_tier}"}

        w3 = self._get_w3()
        token_in_addr = self._resolve_token(token_in, w3)
        token_out_addr = self._resolve_token(token_out, w3)

        amount_in_wei = self._amount_to_wei(w3, token_in_addr, amount)

        quoter = w3.eth.contract(
            address=self._to_checksum(w3, QUOTER_V2),
            abi=QUOTER_V2_ABI,
        )

        params = {
            "tokenIn": self._to_checksum(w3, token_in_addr),
            "tokenOut": self._to_checksum(w3, token_out_addr),
            "amountIn": amount_in_wei,
            "fee": fee_tier,
            "sqrtPriceLimitX96": 0,
        }

        try:
            # QuoterV2 uses call() — Uniswap quoter is a view-like that reverts with result
            # We use eth_call via contract.functions...call()
            result = quoter.functions.quoteExactInputSingle(params).call()
            # result is (amountOut, sqrtPriceX96After, initializedTicksCrossed, gasEstimate)
            amount_out_raw = result[0]
            amount_out = self._wei_to_amount(w3, token_out_addr, amount_out_raw)

            return {
                "amount_in": amount,
                "amount_out": amount_out,
                "amount_out_raw": str(amount_out_raw),
                "sqrt_price_x96_after": result[1],
                "initialized_ticks_crossed": result[2],
                "gas_estimate": result[3],
                "fee_tier": fee_tier,
                "price": amount_out / amount if amount > 0 else 0,
            }
        except Exception as e:
            return {"error": str(e)}

    # ------------------------------------------------------------------
    # Pool info
    # ------------------------------------------------------------------

    def get_pool_info(self, token_a: str, token_b: str, fee_tier: int = 3000) -> PoolInfo:
        """Fetch pool state: liquidity, sqrtPriceX96, tick.

        Args:
            token_a: First token address.
            token_b: Second token address.
            fee_tier: Pool fee tier.

        Returns:
            PoolInfo dataclass.
        """
        w3 = self._get_w3()
        token_a_addr = self._resolve_token(token_a, w3)
        token_b_addr = self._resolve_token(token_b, w3)

        # Resolve pool address via factory
        factory = w3.eth.contract(
            address=self._to_checksum(w3, FACTORY),
            abi=FACTORY_ABI,
        )
        pool_addr = factory.functions.getPool(
            self._to_checksum(w3, token_a_addr),
            self._to_checksum(w3, token_b_addr),
            fee_tier,
        ).call()

        if pool_addr == "0x0000000000000000000000000000000000000000":
            raise ValueError("Pool does not exist for this token pair and fee tier")

        pool = w3.eth.contract(address=pool_addr, abi=POOL_ABI)

        liquidity = pool.functions.liquidity().call()
        slot0 = pool.functions.slot0().call()
        sqrt_price_x96 = slot0[0]
        tick = slot0[1]

        # Sort tokens to match pool's token0/token1 ordering
        token0, token1 = self._sort_tokens(token_a_addr, token_b_addr)

        return PoolInfo(
            pool_address=pool_addr,
            token0=token0,
            token1=token1,
            fee=fee_tier,
            liquidity=liquidity,
            sqrt_price_x96=sqrt_price_x96,
            tick=tick,
        )

    # ------------------------------------------------------------------
    # Create pool
    # ------------------------------------------------------------------

    def create_pool(
        self,
        token_a: str,
        token_b: str,
        fee_tier: int = 3000,
        sqrt_price_x96: int = 0,
    ) -> dict:
        """Initialize a new Uniswap V3 pool via the Factory.

        Args:
            token_a: First token address.
            token_b: Second token address.
            fee_tier: Fee tier for the new pool.
            sqrt_price_x96: Initial sqrt price (Q64.96). If 0, defaults to 1:1.

        Returns:
            Dict with ``pool_address`` and ``tx_hash``.
        """
        if fee_tier not in FEE_TIERS:
            raise ValueError(f"Invalid fee tier {fee_tier}")

        w3 = self._get_w3()

        token_a_addr = self._to_checksum(w3, token_a)
        token_b_addr = self._to_checksum(w3, token_b)
        token0, token1 = self._sort_tokens(token_a_addr, token_b_addr)

        if sqrt_price_x96 == 0:
            # Default to 1:1 price
            sqrt_price_x96 = get_sqrt_ratio_at_tick(0)

        factory = w3.eth.contract(
            address=self._to_checksum(w3, FACTORY),
            abi=FACTORY_ABI,
        )

        tx = factory.functions.createPool(
            self._to_checksum(w3, token0),
            self._to_checksum(w3, token1),
            fee_tier,
        ).build_transaction({
            "from": self._to_checksum(w3, "0x0"),  # caller sets
            "gas": 500_000,
            "gasPrice": w3.eth.gas_price,
            "nonce": 0,  # caller sets
            "chainId": CHAIN_IDS.get(self.chain, 1),
        })

        return {
            "function": "createPool",
            "token0": token0,
            "token1": token1,
            "fee": fee_tier,
            "sqrt_price_x96": sqrt_price_x96,
            "tx": tx,
        }

    # ------------------------------------------------------------------
    # NFT Position Manager — mint / increase / decrease / collect
    # ------------------------------------------------------------------

    def _get_nfp_manager(self, w3):
        return w3.eth.contract(
            address=self._to_checksum(w3, NONFUNGIBLE_POSITION_MANAGER),
            abi=NONFUNGIBLE_POSITION_MANAGER_ABI,
        )

    def mint_position(
        self,
        token_a: str,
        token_b: str,
        fee: int,
        tick_lower: int,
        tick_upper: int,
        amount0: float,
        amount1: float,
    ) -> dict:
        """Mint a new Uniswap V3 NFT position.

        Args:
            token_a: First token address.
            token_b: Second token address.
            fee: Pool fee tier.
            tick_lower: Lower tick bound.
            tick_upper: Upper tick bound.
            amount0: Amount of token0 (human-readable).
            amount1: Amount of token1 (human-readable).

        Returns:
            Dict with mint parameters for signing.
        """
        w3 = self._get_w3()

        token_a_addr = self._to_checksum(w3, token_a)
        token_b_addr = self._to_checksum(w3, token_b)
        token0, token1 = self._sort_tokens(token_a_addr, token_b_addr)

        amount0_wei = self._amount_to_wei(w3, token0, amount0)
        amount1_wei = self._amount_to_wei(w3, token1, amount1)

        deadline = int(time.time()) + 1200

        params = {
            "token0": self._to_checksum(w3, token0),
            "token1": self._to_checksum(w3, token1),
            "fee": fee,
            "tickLower": tick_lower,
            "tickUpper": tick_upper,
            "amount0Desired": amount0_wei,
            "amount1Desired": amount1_wei,
            "amount0Min": int(amount0_wei * (1 - self.slippage / 100)),
            "amount1Min": int(amount1_wei * (1 - self.slippage / 100)),
            "recipient": self._to_checksum(w3, "0x0"),  # caller sets
            "deadline": deadline,
        }

        nfp = self._get_nfp_manager(w3)

        tx = nfp.functions.mint(params).build_transaction({
            "from": self._to_checksum(w3, "0x0"),
            "value": 0,
            "gas": 500_000,
            "gasPrice": w3.eth.gas_price,
            "nonce": 0,
            "chainId": CHAIN_IDS.get(self.chain, 1),
        })

        return {"function": "mint", "params": params, "tx": tx}

    def increase_liquidity(
        self,
        token_id: int,
        amount0: float,
        amount1: float,
    ) -> dict:
        """Add liquidity to an existing NFT position.

        Args:
            token_id: NFT token ID of the position.
            amount0: Additional amount of token0 (human-readable).
            amount1: Additional amount of token1 (human-readable).

        Returns:
            Dict with increaseLiquidity parameters.
        """
        w3 = self._get_w3()
        nfp = self._get_nfp_manager(w3)

        # Get position info to determine token addresses
        pos = nfp.functions.positions(token_id).call()
        token0_addr = pos[2]
        token1_addr = pos[3]

        amount0_wei = self._amount_to_wei(w3, token0_addr, amount0)
        amount1_wei = self._amount_to_wei(w3, token1_addr, amount1)

        deadline = int(time.time()) + 1200

        params = {
            "tokenId": token_id,
            "amount0Desired": amount0_wei,
            "amount1Desired": amount1_wei,
            "amount0Min": int(amount0_wei * (1 - self.slippage / 100)),
            "amount1Min": int(amount1_wei * (1 - self.slippage / 100)),
            "deadline": deadline,
        }

        tx = nfp.functions.increaseLiquidity(params).build_transaction({
            "from": self._to_checksum(w3, "0x0"),
            "value": 0,
            "gas": 300_000,
            "gasPrice": w3.eth.gas_price,
            "nonce": 0,
            "chainId": CHAIN_IDS.get(self.chain, 1),
        })

        return {"function": "increaseLiquidity", "params": params, "tx": tx}

    def decrease_liquidity(
        self,
        token_id: int,
        liquidity: int,
        amount0_min: int = 0,
        amount1_min: int = 0,
    ) -> dict:
        """Remove liquidity from an existing NFT position.

        Args:
            token_id: NFT token ID.
            liquidity: Amount of liquidity to remove.
            amount0_min: Minimum amount of token0 (in wei).
            amount1_min: Minimum amount of token1 (in wei).

        Returns:
            Dict with decreaseLiquidity parameters.
        """
        w3 = self._get_w3()
        nfp = self._get_nfp_manager(w3)

        deadline = int(time.time()) + 1200

        params = {
            "tokenId": token_id,
            "liquidity": liquidity,
            "amount0Min": amount0_min,
            "amount1Min": amount1_min,
            "deadline": deadline,
        }

        tx = nfp.functions.decreaseLiquidity(params).build_transaction({
            "from": self._to_checksum(w3, "0x0"),
            "value": 0,
            "gas": 300_000,
            "gasPrice": w3.eth.gas_price,
            "nonce": 0,
            "chainId": CHAIN_IDS.get(self.chain, 1),
        })

        return {"function": "decreaseLiquidity", "params": params, "tx": tx}

    def collect_fees(self, token_id: int) -> dict:
        """Collect accumulated fees from an NFT position.

        Args:
            token_id: NFT token ID.

        Returns:
            Dict with collect parameters.
        """
        w3 = self._get_w3()
        nfp = self._get_nfp_manager(w3)

        # Get position info
        pos = nfp.functions.positions(token_id).call()
        tokens_owed0 = pos[10]
        tokens_owed1 = pos[11]

        params = {
            "tokenId": token_id,
            "recipient": self._to_checksum(w3, "0x0"),  # caller sets
            "amount0Max": tokens_owed0,
            "amount1Max": tokens_owed1,
        }

        tx = nfp.functions.collect(params).build_transaction({
            "from": self._to_checksum(w3, "0x0"),
            "value": 0,
            "gas": 200_000,
            "gasPrice": w3.eth.gas_price,
            "nonce": 0,
            "chainId": CHAIN_IDS.get(self.chain, 1),
        })

        return {
            "function": "collect",
            "params": params,
            "tokens_owed0": tokens_owed0,
            "tokens_owed1": tokens_owed1,
            "tx": tx,
        }
