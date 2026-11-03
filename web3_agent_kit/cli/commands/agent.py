"""wak agent — run an AI agent."""

import click


@click.command()
@click.option("--goal", "-g", required=True, help="Natural language goal for the agent")
@click.option("--wallet", "-w", required=True, help="Wallet address matching PRIVATE_KEY")
@click.option("--chain", "-c", default="base", help="Target blockchain network")
@click.option("--yes", is_flag=True, help="Skip the transaction-execution confirmation")
def agent(goal, wallet, chain, yes):
    """Run an AI agent with Uniswap swap capability.

    \b
    Example:
      wak agent --goal "swap 0.1 ETH to USDC" --wallet 0x1234... --chain base
      wak agent -g "swap ETH to USDC" -w 0x1234... -c base
    """
    import os

    from web3_agent_kit.agent.core import Agent
    from web3_agent_kit.chains.chain import Chain, ChainManager
    from web3_agent_kit.defi import Uniswap
    from web3_agent_kit.wallet.wallet import Wallet

    try:
        selected_chain = Chain[chain.upper().replace("-", "_")]
    except KeyError as exc:
        raise click.ClickException(f"Unsupported chain: {chain}") from exc
    private_key = os.environ.get("PRIVATE_KEY")
    if not private_key:
        raise click.ClickException("Set PRIVATE_KEY to the key for the requested wallet.")
    rpc_url = os.environ.get(f"{selected_chain.name}_RPC_URL") or os.environ.get("RPC_URL")
    if not rpc_url:
        raise click.ClickException(
            f"Set {selected_chain.name}_RPC_URL or RPC_URL to run on {selected_chain.value}."
        )

    manager = ChainManager([selected_chain], {selected_chain: rpc_url})
    configured_wallet = Wallet.from_env("PRIVATE_KEY", chain_manager=manager)
    if configured_wallet.address.lower() != wallet.lower():
        raise click.ClickException(
            "The supplied --wallet address does not match the account derived from PRIVATE_KEY."
        )
    if not configured_wallet.is_enforced:
        raise click.ClickException(
            "No pre-sign authorization pipeline is configured. The CLI will not run "
            "an agent that can submit transactions without one; bind an authorized "
            "PreSignInterceptor through the Python API."
        )
    if not yes and not click.confirm(
        "The agent may submit on-chain transactions within its configured spend limits. Continue?",
        default=False,
    ):
        raise click.Abort()

    try:
        result = Agent(
            wallet=configured_wallet,
            chains=[selected_chain],
            tools=[Uniswap(chain_manager=manager)],
        ).run(goal)
    except Exception as exc:
        raise click.ClickException(f"Agent execution failed: {exc}") from exc

    click.echo(f"Agent result: {result}")
