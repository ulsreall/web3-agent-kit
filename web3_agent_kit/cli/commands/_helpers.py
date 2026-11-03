"""Shared setup helpers for RPC-backed CLI commands."""

import os

import click

from web3_agent_kit.chains.chain import Chain, ChainManager


def resolve_chain(chain_name: str) -> Chain:
    """Resolve a supported chain name."""
    try:
        return Chain[chain_name.upper().replace("-", "_")]
    except KeyError as exc:
        supported = ", ".join(member.value for member in Chain)
        raise click.ClickException(
            f"Unsupported chain '{chain_name}'. Supported chains: {supported}"
        ) from exc


def chain_manager_for(chain_name: str) -> tuple[Chain, ChainManager]:
    """Resolve a chain and its configured RPC endpoint."""
    chain = resolve_chain(chain_name)
    rpc_url = os.environ.get(f"{chain.name}_RPC_URL") or os.environ.get("RPC_URL")
    if not rpc_url:
        raise click.ClickException(f"Set {chain.name}_RPC_URL or RPC_URL to query {chain.value}.")

    return chain, ChainManager([chain], {chain: rpc_url})


def read_native_balance(address: str, chain: Chain, manager: ChainManager) -> float:
    """Read an address's native-token balance without requiring a private key."""
    if chain == Chain.SOLANA:
        return manager.get_solana().get_balance(address).value / 1e9
    web3 = manager.get_web3(chain)
    return float(web3.from_wei(web3.eth.get_balance(address), "ether"))
