"""Example: Multi-Wallet Manager — Create, manage, batch send across multiple wallets."""

from web3_agent_kit.wallet import MultiWalletManager
from web3_agent_kit import Chain

# Initialize manager
manager = MultiWalletManager(chain=Chain.ETHEREUM)

# 1. Create wallets
main = manager.create_wallet("main", group="trading", tags=["hot"])
airdrop1 = manager.create_wallet("airdrop-01", group="airdrop", tags=["farming"])
airdrop2 = manager.create_wallet("airdrop-02", group="airdrop", tags=["farming"])
sniper = manager.create_wallet("sniper-01", group="trading", tags=["sniper"])

print(f"Created {len(manager.wallets)} wallets")

# 2. Import existing wallet
# imported = manager.import_wallet("cold", private_key="0x...", group="cold")

# 3. List wallets
print("\n=== All Wallets ===")
for w in manager.list_wallets():
    print(f"  [{w.group}] {w.label}: {w.short_address}")

# 4. List by group
print("\n=== Airdrop Wallets ===")
for w in manager.list_wallets(group="airdrop"):
    print(f"  {w.label}: {w.short_address}")

# 5. Groups overview
print("\n=== Groups ===")
for group, labels in manager.get_groups().items():
    print(f"  {group}: {len(labels)} wallets")

# 6. Batch send to multiple recipients
results = manager.batch_send(
    recipients=["0xRecipient1", "0xRecipient2"],
    amount=0.001,
    group_filter="airdrop",
    delay_between=2,
)
for r in results:
    print(f"  {r.wallet_label} -> {r.status}")

# 7. Consolidate funds to main wallet
results = manager.consolidate_to(
    target_label="main",
    group_filter="airdrop",
    keep_minimum=0.0005,
)
for r in results:
    print(f"  Consolidated {r.wallet_label}: {r.status}")

# 8. Export addresses
print("\n=== Export CSV ===")
print(manager.export_addresses(format="csv"))

# 9. Consolidated balance
summary = manager.get_consolidated_balance()
print(f"\nTotal wallets: {summary.wallet_count}")
print(f"Total native: {summary.total_native:.6f}")
