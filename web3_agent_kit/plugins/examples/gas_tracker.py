"""Example plugin — Gas Tracker. Shows how to build a web3-agent-kit plugin."""

from web3_agent_kit.plugins import Plugin, PluginMeta


class GasTrackerPlugin(Plugin):
    """Track gas prices and alert when they're low.

    This plugin monitors gas prices and provides alerts
    when gas drops below a configured threshold.
    """

    @property
    def meta(self) -> PluginMeta:
        return PluginMeta(
            name="gas-tracker",
            version="1.0.0",
            description="Track gas prices and alert when below threshold",
            author="web3-agent-kit",
            hooks=["on_block"],
        )

    def setup(self, agent) -> None:
        self.agent = agent
        self.threshold_gwei = 20  # Alert when gas < 20 gwei
        self.last_gas = 0

    def execute(self, action: str, **kwargs) -> dict:
        if action == "get_gas":
            return self._get_gas()
        elif action == "set_threshold":
            self.threshold_gwei = kwargs.get("threshold", 20)
            return {"threshold": self.threshold_gwei}
        elif action == "is_low":
            return {"is_low": self.last_gas < self.threshold_gwei, "gas": self.last_gas}
        return {"error": f"Unknown action: {action}"}

    def on_block(self, block_number: int) -> None:
        """Check gas on each new block."""
        try:
            w3 = self.agent.wallet.w3
            gas_price = w3.eth.gas_price
            self.last_gas = w3.from_wei(gas_price, "gwei")

            if self.last_gas < self.threshold_gwei:
                print(f"⛽ LOW GAS: {self.last_gas:.1f} gwei (threshold: {self.threshold_gwei})")
        except Exception:
            pass

    def _get_gas(self) -> dict:
        try:
            w3 = self.agent.wallet.w3
            gas_price = w3.eth.gas_price
            gas_gwei = w3.from_wei(gas_price, "gwei")
            return {
                "gas_gwei": gas_gwei,
                "gas_wei": gas_price,
                "is_low": gas_gwei < self.threshold_gwei,
            }
        except Exception as e:
            return {"error": str(e)}


def register_plugin() -> Plugin:
    """Entry point for plugin discovery."""
    return GasTrackerPlugin()
