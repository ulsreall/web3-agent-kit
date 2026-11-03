"""wak gas — gas estimation commands."""

import click

from ._helpers import chain_manager_for


@click.command("gas")
@click.option("--chain", "-c", default="ethereum", help="Blockchain network")
@click.option(
    "--priority",
    "-p",
    default="medium",
    type=click.Choice(["low", "medium", "high", "urgent"]),
    help="Gas priority level",
)
def gas(chain, priority):
    """Show current gas prices for a chain.

    \b
    Example:
      wak gas --chain ethereum
      wak gas -c base -p high
    """
    from web3_agent_kit.gas.optimizer import GasOptimizer, GasPriority
    from web3_agent_kit.wallet.wallet import Wallet, WalletConfig

    selected_chain, manager = chain_manager_for(chain)
    optimizer = GasOptimizer(Wallet(WalletConfig(), chain_manager=manager), manager)
    try:
        price = optimizer.get_gas_price(selected_chain)
    except Exception as exc:
        raise click.ClickException(f"Unable to read gas price: {exc}") from exc

    selected_priority = GasPriority(priority)
    priority_fee = optimizer.PRIORITY_FEES[selected_priority]
    click.echo(f"Chain: {selected_chain.value}")
    click.echo(f"Priority: {selected_priority.value}")
    click.echo(f"Base fee: {price['gwei']} gwei")
    click.echo(f"Priority fee: {priority_fee} gwei")
    click.echo(f"Suggested max fee: {price['gwei'] * 2 + priority_fee} gwei")
    click.echo(f"Estimated native cost for a 21,000 gas transfer: {price['eth'] * 21_000}")
    click.echo(f"Network level: {price['level']}")
