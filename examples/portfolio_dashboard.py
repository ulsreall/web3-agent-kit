#!/usr/bin/env python3
"""
Portfolio tracker example — real-time balances across chains.

Shows portfolio value, token balances, and P&L tracking.

Usage:
    export PRIVATE_KEY="0x..."
    python examples/portfolio_dashboard.py
"""

import os
import sys
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from web3_agent_kit import Wallet, Chain, ChainManager
from web3_agent_kit.portfolio import PortfolioTracker

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def main():
    private_key = os.environ.get("PRIVATE_KEY")
    if not private_key:
        print("❌ Set PRIVATE_KEY environment variable")
        sys.exit(1)

    # Setup chains
    chain_manager = ChainManager(
        chains=[Chain.ETHEREUM, Chain.BASE, Chain.ARBITRUM],
        rpcs={
            Chain.ETHEREUM: os.environ.get("ETH_RPC", "https://eth.llamarpc.com"),
            Chain.BASE: os.environ.get("BASE_RPC", "https://mainnet.base.org"),
            Chain.ARBITRUM: os.environ.get("ARB_RPC", "https://arb1.arbitrum.io/rpc"),
        },
    )

    wallet = Wallet.from_key(private_key, chain_manager=chain_manager)
    print(f"📍 Wallet: {wallet.address}")

    # Create tracker
    tracker = PortfolioTracker(chain_manager, wallet, eth_price=3500.0)

    # Get summary
    print("\n" + "=" * 60)
    summary = tracker.get_summary()
    print(summary)

    # Get JSON
    print("\n📋 JSON:")
    import json
    print(json.dumps(summary.to_dict(), indent=2, default=str))

    # Track P&L (take snapshots over time)
    print("\n📈 P&L Tracking:")
    print("  Take multiple snapshots to track P&L:")
    print("  tracker.get_summary()  # snapshot 1")
    print("  # ... wait some time ...")
    print("  tracker.get_summary()  # snapshot 2")
    print("  pnl = tracker.get_pnl()")


if __name__ == "__main__":
    main()
