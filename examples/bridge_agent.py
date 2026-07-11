#!/usr/bin/env python3
"""
Bridge agent example — cross-chain token transfers.

Find best bridge routes and execute transfers between chains.

Usage:
    export PRIVATE_KEY="0x..."
    python examples/bridge_agent.py
"""

import os
import sys
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from web3_agent_kit import Wallet, Chain, ChainManager
from web3_agent_kit.bridge import BridgeAgent

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

    # Create bridge agent
    bridge = BridgeAgent(chain_manager, wallet)

    # Get routes
    print("\n🔍 Finding bridge routes: 0.01 ETH from Ethereum → Base")
    routes = bridge.get_routes("ETH", 0.01, Chain.ETHEREUM, Chain.BASE)

    if routes:
        print(f"\n📊 Found {len(routes)} routes:")
        for i, route in enumerate(routes):
            print(f"\n  Route {i + 1}: {route.bridge_name}")
            print(f"    Input: {route.amount_in} ETH")
            print(f"    Output: {route.amount_out:.6f} ETH")
            print(f"    Fee: ${route.fee_usd:.2f}")
            print(f"    Time: ~{route.time_estimate // 60} min")
    else:
        print("❌ No routes found")

    # Execute transfer (commented out for safety)
    # print("\n🚀 Executing best route...")
    # result = bridge.transfer("ETH", 0.01, Chain.ETHEREUM, Chain.BASE)
    # print(f"TX Hash: {result.tx_hash}")
    # print(f"ETA: ~{result.estimated_arrival // 60} minutes")

    print("\n💡 Uncomment the transfer section to execute a real bridge transfer.")


if __name__ == "__main__":
    main()
