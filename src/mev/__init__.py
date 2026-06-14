"""MEV Protection — protect transactions from sandwich attacks.

Integrates with Flashbots and private transaction relays to
protect trades from MEV (Maximal Extractable Value) attacks.

Usage::

    from web3_agent_kit.mev import MEVProtector, MEVConfig

    protector = MEVProtector(MEVConfig(
        chain="ethereum",
        use_flashbots=True,
    ))
    protected_tx = protector.protect_tx(raw_tx)
"""

from .frontrun_detection import detect_frontrun
from .mev_strategy import MEVProtector
from .sandwich_protection import check_sandwich_risk
from .utils import BundleResult, MEVConfig, MEVStrategy, ProtectedTx

__all__ = [
    "MEVStrategy",
    "MEVConfig",
    "ProtectedTx",
    "BundleResult",
    "MEVProtector",
    "check_sandwich_risk",
    "detect_frontrun",
]
