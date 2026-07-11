#!/usr/bin/env python3
"""
Direct Uniswap swap — no LLM, just programmatic token swapping.

Shows how to use Uniswap tool directly for swaps and quotes.

Usage:
    export PRIVATE_KEY="0x..."
    python examples/direct_swap.py
"""

import os
import sys
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from web3_agent_kit import Wallet, Chain, ChainManager
from web3_agent_kit.defi import Uniswap

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def main():
    private_key = os.environ.get("PRIVATE_KEY")
    if not private_key:
        print("❌ Set PRIVATE_KEY environment variable")
        sys.exit(1)

    # Setup
    chain_manager = ChainManager(
        chains=[Chain.ETHEREUM, Chain.BASE, Chain.ARBITRUM],
        rpcs={
            Chain.ETHEREUM: os.environ.get("ETH_RPC", "https://eth.llamarpc.com"),
            Chain.BASE: os.environ.get("BASE_RPC", "https://mainnet.base.org"),
            Chain.ARBITRUM: os.environ.get("ARB_RPC", "https://arb1.arbitrum.io/rpc"),
        },
    )

    wallet = Wallet.from_key(private_key, chain_manager=chain_manager)
    uniswap = Uniswap(chain_manager=chain_manager, slippage=0.5)

    print(f"📍 Wallet: {wallet.address}")

    # Get quote first (no transaction)
    print("\n📊 Getting quote: 0.001 ETH → USDC on Base")
    quote = uniswap.get_quote(
        token_in="ETH",
        token_out="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",  # USDC on Base
        amount=0.001,
        chain=Chain.BASE,
    )

    if "error" in quote:
        print(f"❌ Quote error: {quote['error']}")
    else:
        print(f"   Input: {quote['amount_in']} ETH")
        print(f"   Output: {quote['amount_out']:.2f} USDC")
        print(f"   Price: 1 ETH = {quote['price']:.2f} USDC")

    # Resolve token by symbol
    print("\n🔍 Token resolution:")
    for symbol in ["ETH", "USDC", "USDT", "WETH"]:
        try:
            addr = uniswap.resolve_token(symbol, Chain.BASE)
            print(f"   {symbol} → {addr}")
        except ValueError as e:
            print(f"   {symbol} → {e}")

    # Execute swap (uncomment to actually swap)
    # print("\n🔄 Executing swap: 0.001 ETH → USDC on Base")
    # result = uniswap.execute(
    #     wallet=wallet,
    #     token_in="ETH",
    #     token_out="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    #     amount=0.001,
    #     chain=Chain.BASE,
    # )
    # print(f"   TX Hash: {result.tx_hash}")
    # print(f"   Amount Out: {result.amount_out:.2f} USDC")
    # print(f"   Gas Used: {result.gas_used}")

    print("\n💡 Uncomment the swap section in the code to execute a real swap.")


if __name__ == "__main__":
    main()
