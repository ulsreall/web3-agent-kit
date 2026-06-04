"""Example: Plugin System — Load, register, and use plugins."""

from web3_agent_kit.plugins import PluginManager, Plugin, PluginMeta

# === Custom Plugin Example ===

class WhaleWatcherPlugin(Plugin):
    """Monitor whale wallet movements."""

    @property
    def meta(self) -> PluginMeta:
        return PluginMeta(
            name="whale-watcher",
            version="1.0.0",
            description="Monitor whale wallets for large transfers",
            author="Community",
            hooks=["on_block"],
        )

    def setup(self, agent) -> None:
        self.agent = agent
        self.whale_addresses = [
            "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",  # vitalik.eth
        ]
        self.alerts = []

    def execute(self, action: str, **kwargs) -> dict:
        if action == "add_whale":
            addr = kwargs.get("address")
            if addr and addr not in self.whale_addresses:
                self.whale_addresses.append(addr)
            return {"whales": len(self.whale_addresses)}
        elif action == "list_whales":
            return {"whales": self.whale_addresses}
        elif action == "alerts":
            return {"alerts": self.alerts[-10:]}
        return {"error": f"Unknown action: {action}"}

    def on_block(self, block_number: int) -> None:
        """Check for whale activity on each block."""
        # In a real implementation, you'd check the block's transactions
        # against whale_addresses and alert on large transfers
        pass


# === Usage ===

# 1. Create plugin manager
manager = PluginManager()

# 2. Register plugins manually
whale_plugin = WhaleWatcherPlugin()
manager.registry.register(whale_plugin)

# 3. Or discover from directory
# manager.load_dir("./my_plugins/")

# 4. Or discover from installed packages (entry_points)
# manager.load_entry_points()

# 5. List all plugins
print("=== Loaded Plugins ===")
for p in manager.list_plugins():
    print(f"  {p['name']} v{p['version']}: {p['description']}")
    print(f"    Hooks: {p['hooks']}")

# 6. Execute plugin actions
result = manager.execute("whale-watcher", "add_whale", address="0xNewWhale")
print(f"\nWhales tracked: {result}")

result = manager.execute("whale-watcher", "list_whales")
print(f"Whale list: {result}")

# 7. Hooks fire automatically
# manager.on_block(block_number=12345678)
# manager.before_transaction(tx)
# manager.after_transaction(tx, result)
