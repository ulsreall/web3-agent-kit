"""Example: Portfolio tracker — monitor positions across chains."""

import os
import json
from datetime import datetime
from web3_agent_kit import Agent, Wallet, Chain


def main():
    """
    Multi-chain portfolio tracker.

    Features:
    - Track balances across all chains
    - Monitor DeFi positions
    - Calculate total P&L
    - Generate reports
    """
    wallet = Wallet.from_env("PRIVATE_KEY")

    # Track all supported chains
    chains = [
        Chain.ETHEREUM,
        Chain.BASE,
        Chain.ARBITRUM,
        Chain.OPTIMISM,
        Chain.POLYGON,
    ]

    agent = Agent(
        wallet=wallet,
        chains=chains,
        llm="gpt-4",
    )

    print("📊 Portfolio Tracker")
    print(f"💰 Wallet: {wallet.address}")
    print()

    # Strategy: gather all portfolio data
    strategy = """
    Portfolio tracking strategy:

    1. BALANCES:
       - Get native token balance on each chain
       - Get ERC-20 token balances
       - Calculate USD values

    2. DEFI POSITIONS:
       - Check Aave deposits/borrows
       - Check Uniswap LP positions
       - Check staking positions

    3. ANALYSIS:
       - Calculate total portfolio value
       - Identify best/worst performers
       - Suggest rebalancing opportunities
    """

    result = agent.run(strategy)
    print(f"Analysis: {result}")

    # Get balances
    print("\n💰 Chain Balances:")
    total_eth = 0
    balances = {}

    for chain in chains:
        try:
            balance = wallet.get_balance(chain)
            balances[chain.value] = float(balance)
            total_eth += float(balance)
            print(f"  {chain.value:>12}: {balance:.6f} ETH")
        except Exception as e:
            print(f"  {chain.value:>12}: Error - {e}")
            balances[chain.value] = 0

    print(f"\n  {'TOTAL':>12}: {total_eth:.6f} ETH")

    # Save portfolio snapshot
    snapshot = {
        "timestamp": datetime.now().isoformat(),
        "wallet": wallet.address,
        "balances": balances,
        "total_eth": total_eth,
    }

    os.makedirs("portfolio", exist_ok=True)
    path = f"portfolio/snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(path, "w") as f:
        json.dump(snapshot, f, indent=2)

    print(f"\n📝 Snapshot saved to {path}")


if __name__ == "__main__":
    main()
