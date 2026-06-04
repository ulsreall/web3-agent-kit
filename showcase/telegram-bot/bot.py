"""Telegram Bot Template — Ready-to-deploy showcase for web3-agent-kit.

Features:
- /balance — Check wallet balance across chains
- /swap — Token swap via Uniswap
- /portfolio — Full portfolio view
- /dca — Create/manage DCA orders
- /snipe — Token sniper controls
- /bridge — Cross-chain bridge
- /gas — Check gas prices

Setup:
    1. Get bot token from @BotFather
    2. Set TELEGRAM_BOT_TOKEN env var
    3. Set PRIVATE_KEY env var
    4. pip install web3-agent-kit python-telegram-bot
    5. python bot.py
"""

import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# web3-agent-kit imports
from web3_agent_kit import (
    Wallet,
    Chain,
    ChainManager,
    PortfolioTracker,
    YieldOptimizer,
    YieldConfig,
    MultiWalletManager,
)
from web3_agent_kit.dca_bot import DCABot, Interval, DCAStatus

# === Config ===
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
PRIVATE_KEY = os.environ.get("PRIVATE_KEY", "")
OWNER_ID = int(os.environ.get("TELEGRAM_OWNER_ID", "0"))

# === Initialize ===
chain_manager = ChainManager(chains=[Chain.ETHEREUM, Chain.BASE, Chain.ARBITRUM])
wallet = None
portfolio = None
dca_bot = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init_wallet():
    """Initialize wallet from env."""
    global wallet, portfolio, dca_bot
    if PRIVATE_KEY:
        wallet = Wallet.from_key(PRIVATE_KEY, chain_manager=chain_manager)
        portfolio = PortfolioTracker(chain_manager, wallet)
        dca_bot = DCABot(wallet, chain_manager)
        logger.info("✅ Wallet initialized")
    else:
        logger.warning("⚠️ No PRIVATE_KEY set — running in demo mode")


# === Command Handlers ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome message."""
    keyboard = [
        [
            InlineKeyboardButton("💰 Balance", callback_data="balance"),
            InlineKeyboardButton("📊 Portfolio", callback_data="portfolio"),
        ],
        [
            InlineKeyboardButton("💱 Swap", callback_data="swap"),
            InlineKeyboardButton("🌉 Bridge", callback_data="bridge"),
        ],
        [
            InlineKeyboardButton("📈 DCA", callback_data="dca"),
            InlineKeyboardButton("🌾 Yield", callback_data="yield"),
        ],
        [
            InlineKeyboardButton("⛽ Gas", callback_data="gas"),
            InlineKeyboardButton("🔫 Sniper", callback_data="sniper"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🤖 *Web3 Agent Kit Bot*\n\n"
        "Your autonomous DeFi assistant. Pick a command:\n\n"
        "Powered by [web3-agent-kit](https://github.com/ulsreall/web3-agent-kit)",
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )


async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check wallet balance."""
    if not wallet:
        await update.message.reply_text("❌ No wallet configured. Set PRIVATE_KEY.")
        return

    msg = await update.message.reply_text("⏳ Fetching balance...")

    try:
        bal = wallet.get_balance()
        native = bal.get("native", 0)
        tokens = bal.get("tokens", {})

        text = f"💰 *Balance*\n\n"
        text += f"ETH: `{native:.6f}`\n"

        for symbol, amount in tokens.items():
            if amount > 0:
                text += f"{symbol}: `{amount:.4f}`\n"

        text += f"\n📍 `{wallet.address[:10]}...{wallet.address[-6:]}`"

        await msg.edit_text(text, parse_mode="Markdown")
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")


async def portfolio_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show full portfolio."""
    if not portfolio:
        await update.message.reply_text("❌ No wallet configured.")
        return

    msg = await update.message.reply_text("⏳ Loading portfolio...")

    try:
        summary = portfolio.get_summary()

        text = f"📊 *Portfolio*\n\n"
        text += f"💰 Total: `${summary.get('total_value_usd', 0):,.2f}`\n\n"

        for chain_name, chain_data in summary.get("chains", {}).items():
            text += f"🔗 *{chain_name}*: ${chain_data.get('value_usd', 0):,.2f}\n"
            for token, amount in chain_data.get("tokens", {}).items():
                if amount > 0:
                    text += f"  {token}: {amount:.4f}\n"

        await msg.edit_text(text, parse_mode="Markdown")
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")


async def dca_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """DCA management."""
    if not dca_bot:
        await update.message.reply_text("❌ No wallet configured.")
        return

    keyboard = [
        [InlineKeyboardButton("📋 My Orders", callback_data="dca_list")],
        [InlineKeyboardButton("➕ New DCA", callback_data="dca_new")],
        [InlineKeyboardButton("📊 Summary", callback_data="dca_summary")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "📈 *DCA Bot*\n\n"
        "Dollar-Cost Average into any token automatically.\n\n"
        "Choose an action:",
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )


async def dca_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List DCA orders."""
    query = update.callback_query
    await query.answer()

    orders = dca_bot.list_orders()
    if not orders:
        await query.edit_message_text("📋 No DCA orders yet.\n\nUse /dca to create one.")
        return

    text = "📋 *DCA Orders*\n\n"
    for order in orders:
        status_emoji = {"active": "🟢", "paused": "⏸️", "completed": "✅", "cancelled": "❌"}
        emoji = status_emoji.get(order.status.value, "⚪")

        text += (
            f"{emoji} `{order.id[:20]}...`\n"
            f"  {order.from_token} → {order.to_token}\n"
            f"  ${order.amount_per_buy} / {order.interval.name}\n"
            f"  Executions: {order.execution_count} | Spent: ${order.total_spent:.2f}\n\n"
        )

    await query.edit_message_text(text, parse_mode="Markdown")


async def dca_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """DCA portfolio summary."""
    query = update.callback_query
    await query.answer()

    summary = dca_bot.get_summary()

    text = (
        f"📊 *DCA Summary*\n\n"
        f"🟢 Active: {summary['active_orders']}\n"
        f"✅ Completed: {summary['completed_orders']}\n"
        f"💰 Total Spent: ${summary['total_spent']:,.2f}\n"
        f"📦 Total Bought: {summary['total_bought']:.6f}\n"
        f"🔄 Executions: {summary['total_executions']}\n"
        f"📈 Avg Price: ${summary['average_price']:.2f}\n"
    )

    await query.edit_message_text(text, parse_mode="Markdown")


async def gas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check gas prices."""
    msg = await update.message.reply_text("⛽ Checking gas...")

    try:
        from web3 import Web3
        w3 = Web3(Web3.HTTPProvider(chain_manager.get_rpc(Chain.ETHEREUM)))
        gas_price = w3.eth.gas_price
        gas_gwei = w3.from_wei(gas_price, "gwei")

        text = f"⛽ *Gas Price*\n\n"
        text += f"Ethereum: `{gas_gwei:.1f}` gwei\n"

        if gas_gwei < 20:
            text += "\n🟢 Low — good time to transact!"
        elif gas_gwei < 50:
            text += "\n🟡 Normal"
        else:
            text += "\n🔴 High — consider waiting"

        await msg.edit_text(text, parse_mode="Markdown")
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help message."""
    text = (
        "🤖 *Web3 Agent Kit Bot — Commands*\n\n"
        "/start — Main menu\n"
        "/balance — Wallet balance\n"
        "/portfolio — Full portfolio\n"
        "/dca — DCA bot management\n"
        "/gas — Gas prices\n"
        "/help — This message\n\n"
        "🔗 [GitHub](https://github.com/ulsreall/web3-agent-kit)\n"
        "📦 `pip install web3-agent-kit`"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline button presses."""
    query = update.callback_query
    await query.answer()

    if query.data == "balance":
        await balance(update, context)
    elif query.data == "portfolio":
        await portfolio_cmd(update, context)
    elif query.data == "dca":
        await dca_cmd(update, context)
    elif query.data == "dca_list":
        await dca_list(update, context)
    elif query.data == "dca_summary":
        await dca_summary(update, context)
    elif query.data == "gas":
        await gas(update, context)
    else:
        await query.edit_message_text(f"🔜 `{query.data}` — coming soon!")


# === Main ===

def main():
    """Start the bot."""
    if not BOT_TOKEN:
        print("❌ Set TELEGRAM_BOT_TOKEN env var")
        print("   Get one from @BotFather on Telegram")
        return

    init_wallet()

    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("portfolio", portfolio_cmd))
    app.add_handler(CommandHandler("dca", dca_cmd))
    app.add_handler(CommandHandler("gas", gas))

    # Buttons
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Web3 Agent Kit Bot started!")
    print(f"   Wallet: {'✅' if wallet else '❌ (demo mode)'}")
    app.run_polling()


if __name__ == "__main__":
    main()
