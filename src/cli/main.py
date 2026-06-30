"""WAK CLI — Web3 Agent Kit command-line interface."""

import click

from src.cli.commands.agent import agent
from src.cli.commands.doctor import doctor
from src.cli.commands.examples import examples
from src.cli.commands.gas import gas
from src.cli.commands.info import info
from src.cli.commands.token import token
from src.cli.commands.wallet import wallet

BANNER = r"""
 ██╗    ██╗ █████╗ ██╗
 ██║    ██║██╔══██╗██║
 ██║ █╗ ██║███████║██║
 ██║███╗██║██╔══██║██║
 ╚███╔███╔╝██║  ██║██║
  ╚══╝╚══╝ ╚═╝  ╚═╝╚═╝
  Web3 Agent Kit CLI
"""


@click.group(invoke_without_command=True)
@click.version_option(version="1.8.0", prog_name="wak")
@click.pass_context
def main(ctx):
    """WAK — Web3 Agent Kit CLI.

    Build and run autonomous Web3 AI agents from your terminal.

    Run 'wak <command> --help' for more info on a command.
    """
    if ctx.invoked_subcommand is None:
        click.echo(click.style(BANNER, fg="cyan", bold=True))
        click.echo(ctx.get_help())


# Register subcommands
main.add_command(info)
main.add_command(doctor)
main.add_command(wallet)
main.add_command(token)
main.add_command(gas)
main.add_command(agent)
main.add_command(examples)


if __name__ == "__main__":
    main()
