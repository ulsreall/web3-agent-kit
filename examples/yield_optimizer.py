"""Example: Yield optimizer — finds and executes best yield opportunities."""

import os
from web3_agent_kit import Agent, Wallet, Chain
from web3_agent_kit.defi import Aave, Uniswap


def main():
    wallet = Wallet.from_env("PRIVATE_KEY")

    agent = Agent(
        wallet=wallet,
        chains=[Chain.ETHEREUM, Chain.BASE],
        tools=[Aave(), Uniswap()],
        llm="gpt-4",
    )

    # Find and optimize yield
    result = agent.run(
        "Analyze yield opportunities across Ethereum and Base. "
        "Find stablecoin pools with >5% APY and low risk. "
        "Move funds to the best opportunity if current yield is below 3%."
    )
    print(f"Optimization result: {result}")


if __name__ == "__main__":
    main()
