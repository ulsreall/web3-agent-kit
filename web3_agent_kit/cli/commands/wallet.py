"""wak wallet — wallet-related commands."""

import click

from ._helpers import chain_manager_for, read_native_balance


@click.group()
def wallet():
    """Wallet operations (balance, send, etc.)."""
    pass


@wallet.command()
@click.option("--address", "-a", required=True, help="Wallet address (0x...)")
@click.option(
    "--chain", "-c", default="ethereum", help="Blockchain network (ethereum, base, arbitrum, etc.)"
)
def balance(address, chain):
    """Check native token balance for a wallet address.

    \b
    Example:
      wak wallet balance --address 0x1234...abcd --chain ethereum
      wak wallet balance -a 0x1234...abcd -c base
    """
    selected_chain, manager = chain_manager_for(chain)
    try:
        balance = read_native_balance(address, selected_chain, manager)
    except Exception as exc:
        raise click.ClickException(f"Unable to read balance: {exc}") from exc

    click.echo(f"Address: {address}")
    click.echo(f"Chain: {selected_chain.value}")
    click.echo(f"Balance: {balance}")
