"""wak gas — gas estimation commands."""

import click


@click.command("gas")
@click.option("--chain", "-c", default="ethereum", help="Blockchain network")
@click.option("--priority", "-p", default="medium", type=click.Choice(["low", "medium", "high", "urgent"]),
              help="Gas priority level")
def gas(chain, priority):
    """Show current gas prices for a chain.

    \b
    Example:
      wak gas --chain ethereum
      wak gas -c base -p high
    """
    click.echo()
    click.echo(click.style("  ⛽ Gas Price Estimator", fg="cyan", bold=True))
    click.echo()
    click.echo(f"  Chain:    {chain}")
    click.echo(f"  Priority: {priority}")
    click.echo()
    click.echo(click.style("  ⚠️  This command requires an RPC connection.", fg="yellow"))
    click.echo()
    click.echo("  To use this feature, set your RPC URL:")
    click.echo(click.style("    export RPC_URL=https://eth.llamarpc.com", fg="green"))
    click.echo()
    click.echo("  Or use the Python API directly:")
    click.echo(click.style('    from web3_agent_kit import GasOptimizer', fg="green"))
    click.echo(click.style('    optimizer = GasOptimizer(rpc_url="...")', fg="green"))
    click.echo(click.style('    estimate = optimizer.get_estimate("ethereum")', fg="green"))
    click.echo(click.style('    print(f"Low: {estimate.low} | Med: {estimate.medium} | High: {estimate.high}")', fg="green"))
    click.echo()
