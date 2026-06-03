"""Example: Simple swap agent — swaps tokens on Base."""

import os
from web3_agent_kit import Agent, Wallet, Chain
from web3_agent_kit.defi import Uniswap


def main():
    # Load wallet from environment
    wallet = Wallet.from_env("PRIVATE_KEY")

    # Create agent with Uniswap on Base
    agent = Agent(
        wallet=wallet,
        chains=[Chain.BASE],
        tools=[Uniswap()],
        llm="gpt-4",
    )

    # Run a swap task
    result = agent.run("Swap 0.01 ETH to USDC on Base using the best route")
    print(f"Result: {result}")

    # Check balance after
    balance = wallet.get_balance(Chain.BASE)
    print(f"Base balance: {balance} ETH")


if __name__ == "__main__":
    main()
