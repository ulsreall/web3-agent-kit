"""Example: Token sniper — detect and snipe new token launches."""

import os
import time
from datetime import datetime
from web3_agent_kit import Agent, Wallet, Chain
from web3_agent_kit.defi import Uniswap


def main():
    """
    Token launch sniper agent.

    Features:
    - Monitor mempool for new liquidity adds
    - Auto-buy within same block
    - Configurable buy amount and slippage
    - Take-profit and stop-loss management
    """
    wallet = Wallet.from_env("PRIVATE_KEY")

    # Sniper configuration
    config = {
        "chain": Chain.BASE,
        "buy_amount": 0.01,  # ETH
        "max_slippage": 10,  # percent
        "take_profit": 2.0,  # 2x
        "stop_loss": 0.5,    # 50% loss
        "auto_sell": True,
        "blacklist": [       # Token addresses to avoid
            "0xdead",
            "0x0000",
        ],
    }

    agent = Agent(
        wallet=wallet,
        chains=[config["chain"]],
        tools=[Uniswap()],
        llm="gpt-4",
    )

    print("🔫 Token Sniper Agent")
    print(f"📍 Chain: {config['chain'].value}")
    print(f"💰 Buy amount: {config['buy_amount']} ETH")
    print(f"📈 Take profit: {config['take_profit']}x")
    print(f"📉 Stop loss: {config['stop_loss'] * 100}%")
    print()

    # Define sniper strategy
    strategy = f"""
    Token sniper strategy:

    1. MONITOR:
       - Watch for new liquidity adds on Uniswap V2/V3
       - Filter for tokens with > $1000 initial liquidity
       - Check contract verified on explorer
       - Avoid blacklisted addresses: {config['blacklist']}

    2. ANALYZE:
       - Check if contract is renounced
       - Verify no honeypot patterns
       - Check holder distribution
       - Verify liquidity locked

    3. EXECUTE:
       - Buy {config['buy_amount']} ETH worth
       - Max slippage: {config['max_slippage']}%
       - Set take profit at {config['take_profit']}x
       - Set stop loss at {config['stop_loss'] * 100}%

    4. MANAGE:
       - Monitor position P&L
       - Auto-sell at take profit or stop loss
       - Log all trades for analysis
    """

    print("⏳ Monitoring for new launches...")
    print("Press Ctrl+C to stop")
    print()

    try:
        result = agent.run(strategy)
        print(f"✅ Result: {result}")
    except KeyboardInterrupt:
        print("\n⏹️ Sniper stopped by user")


if __name__ == "__main__":
    main()
