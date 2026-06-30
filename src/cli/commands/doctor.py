"""wak doctor — check environment health."""

import importlib
import os
import sys

import click


def _check(label: str, ok: bool, detail: str = "") -> bool:
    """Print a check result and return success status."""
    icon = click.style("  ✅", fg="green") if ok else click.style("  ❌", fg="red")
    msg = f"{icon} {label}"
    if detail:
        msg += click.style(f"  ({detail})", dim=True)
    click.echo(msg)
    return ok


@click.command()
def doctor():
    """Check environment: Python version, dependencies, and wallet config."""
    click.echo(click.style("\n  🩺 WAK Doctor — Environment Check\n", fg="cyan", bold=True))

    all_ok = True

    # ── Python version ──
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    py_ok = sys.version_info >= (3, 10)
    all_ok &= _check("Python >= 3.10", py_ok, py_ver)

    # ── Core dependencies ──
    deps = [
        ("web3", "web3"),
        ("eth_account", "eth-account"),
        ("dotenv", "python-dotenv"),
        ("requests", "requests"),
        ("httpx", "httpx"),
        ("click", "click"),
    ]
    for mod_name, display_name in deps:
        try:
            mod = importlib.import_module(mod_name)
            ver = getattr(mod, "__version__", "installed")
            all_ok &= _check(display_name, True, str(ver))
        except ImportError:
            all_ok &= _check(display_name, False, "not installed")

    # ── .env file ──
    click.echo()
    env_path = os.path.join(os.getcwd(), ".env")
    env_exists = os.path.isfile(env_path)
    all_ok &= _check(".env file", env_exists, env_path if env_exists else "not found")

    # Check key env vars
    env_vars = [
        ("PRIVATE_KEY", "Wallet private key"),
        ("RPC_URL", "RPC endpoint"),
        ("OPENAI_API_KEY", "OpenAI API key (for LLM agent)"),
        ("ETHERSCAN_API_KEY", "Etherscan API key (optional)"),
    ]
    # Load .env if present
    if env_exists:
        try:
            from dotenv import load_dotenv
            load_dotenv(env_path, override=False)
        except Exception:
            pass

    click.echo(click.style("  📋 Environment Variables:", fg="yellow"))
    for var, desc in env_vars:
        val = os.environ.get(var)
        if val:
            masked = val[:6] + "..." + val[-4:] if len(val) > 12 else "***"
            click.echo(click.style("    ✅ ", fg="green") + f"{var} = {masked}")
        else:
            click.echo(click.style("    ⬜ ", dim=True) + f"{var} — {desc}")

    # ── Summary ──
    click.echo()
    if all_ok:
        click.echo(click.style("  🎉 All checks passed! You're ready to use WAK.\n", fg="green", bold=True))
    else:
        click.echo(click.style("  ⚠️  Some checks failed. Fix issues above for full functionality.\n", fg="yellow", bold=True))
