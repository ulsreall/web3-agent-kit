"""Example: DCA Bot — Dollar-Cost Average into tokens automatically."""

from web3_agent_kit import Wallet, Chain, ChainManager
from web3_agent_kit.trading import DCABot, Interval, DCAStatus

# Initialize
chain_manager = ChainManager(chains=[Chain.ETHEREUM, Chain.BASE])
wallet = Wallet.from_env("PRIVATE_KEY", chain_manager=chain_manager)
bot = DCABot(wallet, chain_manager)

# 1. Create DCA orders
print("=== Creating DCA Orders ===")

# Buy $100 of ETH every day on Base
eth_order = bot.create_order(
    from_token="USDC",
    to_token="ETH",
    amount=100,
    chain=Chain.BASE,
    interval=Interval.DAILY,
)
print(f"Created: {eth_order.id}")

# Buy $50 of WBTC every week on Ethereum
btc_order = bot.create_order(
    from_token="USDC",
    to_token="WBTC",
    amount=50,
    chain=Chain.ETHEREUM,
    interval=Interval.WEEKLY,
    max_buys=52,  # 1 year
)
print(f"Created: {btc_order.id}")

# Buy $200 of ETH every month (long-term accumulation)
bot.create_order(
    from_token="USDC",
    to_token="ETH",
    amount=200,
    chain=Chain.ETHEREUM,
    interval=Interval.MONTHLY,
    max_total=2400,  # Stop after $2400 total
)

# 2. Execute immediately (optional)
print("\n=== Execute Now ===")
result = bot.execute_order(eth_order.id)
if result.success:
    print(f"Bought {result.amount_received:.6f} ETH @ ${result.price:.2f}")
else:
    print(f"Failed: {result.error}")

# 3. Register callback for notifications
def on_buy(result):
    print(f"🔔 DCA: {result.amount_spent} spent → {result.amount_received:.6f} bought")

bot.on_execution(on_buy)

# 4. Check status
print("\n=== Orders ===")
for order in bot.list_orders():
    print(f"  [{order.status.value}] {order.from_token}→{order.to_token}: "
          f"${order.amount_per_buy}/{order.interval.name}")

# 5. Cost average analysis
avg = bot.get_cost_average(eth_order.id)
print(f"\n=== Cost Average ===")
print(f"  Avg price: ${avg.get('average_price', 0):.2f}")
print(f"  Range: {avg.get('price_range', 'N/A')}")

# 6. Summary
summary = bot.get_summary()
print(f"\n=== Summary ===")
print(f"  Active: {summary['active_orders']}")
print(f"  Total spent: ${summary['total_spent']:,.2f}")
print(f"  Total bought: {summary['total_bought']:.6f}")

# 7. Run the bot (blocking)
# bot.run(check_interval=60)
