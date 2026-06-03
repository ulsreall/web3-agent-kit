"""Example: Airdrop farmer — multi-chain airdrop farming with tracking."""

import os
import json
from datetime import datetime
from web3_agent_kit import Agent, Wallet, Chain
from web3_agent_kit.defi import Uniswap, Aerodrome


def main():
    """
    Autonomous airdrop farming agent.

    Features:
    - Multi-wallet management
    - Cross-chain activity tracking
    - Quest completion automation
    - Eligibility monitoring
    """
    # Load wallet
    wallet = Wallet.from_env("PRIVATE_KEY")

    # Define target chains for airdrop farming
    chains = [Chain.BASE, Chain.ARBITRUM, Chain.OPTIMISM, Chain.LINEA]

    # Create agent with DeFi tools
    agent = Agent(
        wallet=wallet,
        chains=chains,
        tools=[Uniswap(), Aerodrome()],
        llm="gpt-4",
    )

    # Define farming strategy
    strategy = """
    Airdrop farming strategy:

    1. BASE:
       - Swap small amounts on Aerodrome (weekly)
       - Provide liquidity to stablecoin pools
       - Bridge from Ethereum mainnet

    2. ARBITRUM:
       - Use GMX for trading
       - Interact with Radiant for lending
       - Vote on governance proposals

    3. OPTIMISM:
       - Delegate OP tokens
       - Use Velodrome for swaps
       - Complete RetroPGF quests

    4. GENERAL:
       - Maintain consistent activity (2-3 tx per week per chain)
       - Keep small balances on each chain
       - Document all transactions for tracking
    """

    # Run farming agent
    print("🚀 Starting airdrop farming agent...")
    print(f"📍 Target chains: {', '.join(c.value for c in chains)}")
    print(f"💰 Wallet: {wallet.address}")
    print()

    result = agent.run(strategy)
    print(f"✅ Result: {result}")

    # Check balances across chains
    print("\n📊 Current balances:")
    for chain in chains:
        try:
            balance = wallet.get_balance(chain)
            print(f"  {chain.value}: {balance:.4f} ETH")
        except Exception as e:
            print(f"  {chain.value}: Error - {e}")

    # Save farming log
    log = {
        "timestamp": datetime.now().isoformat(),
        "wallet": wallet.address,
        "chains": [c.value for c in chains],
        "result": result,
    }

    log_path = f"logs/farming_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    os.makedirs("logs", exist_ok=True)
    with open(log_path, "w") as f:
        json.dump(log, f, indent=2)

    print(f"\n📝 Log saved to {log_path}")


if __name__ == "__main__":
    main()
