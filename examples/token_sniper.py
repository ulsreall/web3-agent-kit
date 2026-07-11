#!/usr/bin/env python3
"""
Token sniper example — monitor new liquidity pools and auto-buy.

Monitors Base chain for new Uniswap V2 pairs,
analyzes safety, and buys if safe.

Usage:
    export PRIVATE_KEY="0x..."
    python examples/token_sniper.py
"""

import os
import sys
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from web3_agent_kit import Wallet, Chain, ChainManager
from web3_agent_kit.defi import Uniswap
from web3_agent_kit.trading import TokenSniper, SniperConfig, RiskLevel

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def main():
    private_key = os.environ.get("PRIVATE_KEY")
    if not private_key:
        print("❌ Set PRIVATE_KEY environment variable")
        sys.exit(1)

    # Setup
    chain_manager = ChainManager(
        chains=[Chain.BASE],
        rpcs={
            Chain.BASE: os.environ.get("BASE_RPC", "https://mainnet.base.org"),
        },
    )

    wallet = Wallet.from_key(private_key, chain_manager=chain_manager)
    uniswap = Uniswap(chain_manager=chain_manager, slippage=2.0)

    print(f"📍 Wallet: {wallet.address}")

    # Configure sniper
    config = SniperConfig(
        max_buy=0.005,          # max 0.005 ETH per snipe
        auto_buy=False,         # manual mode for demo
        honeypot_check=True,
        min_liquidity=0.5,      # min 0.5 ETH liquidity
        callback=lambda pair: print(f"\n🔔 NEW PAIR: {pair.token_symbol} ({pair.risk_level.value})"),
    )

    sniper = TokenSniper(
        chain_manager=chain_manager,
        wallet=wallet,
        config=config,
        uniswap=uniswap,
    )

    print(f"🔫 Sniper: {sniper}")

    # Scan recent blocks
    print("\n🔍 Scanning last 100 blocks on Base...")
    pairs = sniper.scan_recent_blocks(num_blocks=100, chain=Chain.BASE)

    print(f"\n📊 Found {len(pairs)} new pairs:")
    for pair in pairs:
        risk_emoji = {
            RiskLevel.LOW: "🟢",
            RiskLevel.MEDIUM: "🟡",
            RiskLevel.HIGH: "🟠",
            RiskLevel.SCAM: "🔴",
        }
        print(f"  {risk_emoji[pair.risk_level]} {pair.token_symbol} — "
              f"LIQ: {pair.liquidity_eth:.2f} ETH | Score: {pair.score:.1f}")

    # Start live monitoring (optional)
    # print("\n🚀 Starting live monitor (Ctrl+C to stop)...")
    # sniper.start(chain=Chain.BASE, poll_interval=12)
    #
    # try:
    #     while True:
    #         time.sleep(1)
    # except KeyboardInterrupt:
    #     sniper.stop()
    #     print("\n⏹ Stopped")


if __name__ == "__main__":
    main()
