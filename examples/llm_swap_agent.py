#!/usr/bin/env python3
"""
LLM-powered swap agent — natural language token swapping.

This example shows how to use the Agent with LLM reasoning
to execute swaps based on natural language instructions.

Usage:
    export PRIVATE_KEY="0x..."
    export OPENAI_API_KEY="sk-..."  # or ANTHROPIC_API_KEY, GROQ_API_KEY, etc.
    python examples/llm_swap_agent.py
"""

import os
import sys
import logging

# Add parent directory to path for local development
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src import Agent, Wallet, Chain, ChainManager
from src.defi import Uniswap

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def main():
    # Load wallet from environment
    private_key = os.environ.get("PRIVATE_KEY")
    if not private_key:
        print("❌ Set PRIVATE_KEY environment variable")
        print("   export PRIVATE_KEY='0x...'")
        sys.exit(1)

    # Setup chain manager
    chain_manager = ChainManager(
        chains=[Chain.ETHEREUM, Chain.BASE, Chain.ARBITRUM],
        rpcs={
            Chain.ETHEREUM: os.environ.get("ETH_RPC", "https://eth.llamarpc.com"),
            Chain.BASE: os.environ.get("BASE_RPC", "https://mainnet.base.org"),
            Chain.ARBITRUM: os.environ.get("ARB_RPC", "https://arb1.arbitrum.io/rpc"),
        },
    )

    # Create wallet
    wallet = Wallet.from_key(private_key, chain_manager=chain_manager)
    print(f"📍 Wallet: {wallet.address}")

    # Check balances
    for chain in [Chain.ETHEREUM, Chain.BASE]:
        try:
            balance = wallet.get_balance(chain)
            print(f"   {chain.value}: {balance:.4f} ETH")
        except Exception as e:
            print(f"   {chain.value}: error ({e})")

    # Create DeFi tools
    uniswap = Uniswap(chain_manager=chain_manager, slippage=1.0)

    # Create agent with LLM reasoning
    agent = Agent(
        wallet=wallet,
        chains=[Chain.BASE],
        tools=[uniswap],
        llm="auto",
        max_steps=10,
        verbose=True,
    )

    print(f"\n🤖 Agent created: {agent}")

    # Run agent with natural language goal
    print("\n" + "=" * 60)
    print("🎯 Goal: Swap 0.001 ETH to USDC on Base")
    print("=" * 60)

    result = agent.run("Swap 0.001 ETH to USDC on Base chain. Use Uniswap.")

    print(f"\n✅ Result: {result}")

    # Show history
    print("\n📋 Action History:")
    for h in agent.get_history():
        print(f"  Step {h['step']}: {h['action'].get('tool')} → {str(h['result'])[:100]}")


if __name__ == "__main__":
    main()
