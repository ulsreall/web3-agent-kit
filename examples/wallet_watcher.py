"""Example: Wallet Watcher — Monitor whale wallets."""

from web3_agent_kit import Chain, ChainManager
from web3_agent_kit.wallet_watcher import WalletWatcher, AlertSeverity

watcher = WalletWatcher(ChainManager(chains=[Chain.ETHEREUM, Chain.BASE]))

# 1. Add wallets to watch
watcher.add_wallet(
    "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
    "vitalik.eth",
    Chain.ETHEREUM,
    alert_threshold_usd=100000,
    tags=["whale", "founder"],
)

watcher.add_wallet(
    "0x28C6c06298d514Db089934071355E5743bf21d60",
    "Binance Hot Wallet",
    Chain.ETHEREUM,
    alert_threshold_usd=500000,
    tags=["exchange", "whale"],
)

# 2. Register alert callback
def on_alert(alert):
    print(f"🔔 [{alert.severity.value}] {alert.wallet_label}: {alert.message}")

watcher.on_alert(on_alert)

# 3. Check all wallets
alerts = watcher.check_all()
print(f"Found {len(alerts)} new alerts")

# 4. Get summary
summary = watcher.get_summary()
print(f"\nWatching {summary['watched_wallets']} wallets")
for w in summary['wallets']:
    print(f"  {w['label']}: {w['address']} ({w['chain']})")

# 5. Snapshot
snapshots = watcher.snapshot_all()
for snap in snapshots:
    print(f"\n{snap.address[:10]}...: {snap.native_balance:.4f} ETH")

# 6. Start monitoring (blocking)
# watcher.start(interval=60)
