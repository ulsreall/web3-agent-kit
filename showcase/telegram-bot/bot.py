"""
Web3 Agent Telegram Bot
A showcase bot built with web3-agent-kit

Features:
- Check wallet balances (ETH + tokens)
- Swap tokens on Uniswap
- Monitor portfolio P&L
- Track new token pairs
- Bridge assets across chains

Usage:
1. pip install web3-agent-kit python-telegram-bot
2. Set TELEGRAM_BOT_TOKEN in .env
3. python bot.py
"""

import os
import logging
from typing import Dict, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

from web3_agent_kit import Agent, Wallet, Governor, Chain

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot configuration
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', 'YOUR_BOT_TOKEN')
DEFAULT_CHAIN = 'ethereum'


class Web3Bot:
    """Telegram bot for Web3 operations using web3-agent-kit"""
    
    def __init__(self):
        self.agents: Dict[int, Agent] = {}
        self.chains = {
            'ethereum': Chain.ETHEREUM,
            'base': Chain.BASE,
            'arbitrum': Chain.ARBITRUM,
            'optimism': Chain.OPTIMISM,
            'polygon': Chain.POLYGON,
        }
    
    def get_or_create_agent(self, user_id: int, chain: str = DEFAULT_CHAIN) -> Agent:
        """Get or create agent for user"""
        if user_id not in self.agents:
            wallet = Wallet(os.getenv('WALLET_ADDRESS', '0x...'))
            governor = Governor(per_tx=0.01, daily=0.1)
            self.agents[user_id] = Agent(
                wallet=wallet,
                governor=governor,
                chain=self.chains.get(chain, Chain.ETHEREUM)
            )
        return self.agents[user_id]
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        welcome = """
🤖 **Web3 Agent Bot**

Built with [web3-agent-kit](https://github.com/ulsreall/web3-agent-kit)

**Commands:**
/balance - Check wallet balance
/swap <amount> <from> <to> - Swap tokens
/portfolio - View portfolio
/snipe <token> - Monitor new pairs
/bridge <amount> <token> <chain> - Bridge assets
/chain <name> - Switch chain

**Supported Chains:**
Ethereum, Base, Arbitrum, Optimism, Polygon

**Example:**
`/swap 0.1 ETH USDC`
`/bridge 100 USDC arbitrum`
"""
        await update.message.reply_text(welcome, parse_mode='Markdown')
    
    async def balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Check wallet balance"""
        agent = self.get_or_create_agent(update.effective_user.id)
        
        await update.message.reply_text('⏳ Checking balance...')
        
        try:
            result = await agent.get_balance()
            
            balance_text = f"""
💰 **Wallet Balance**

**Native:** {result['native']} {result['symbol']}
**USD Value:** ${result['usd_value']:.2f}

**Top Tokens:**
"""
            for token in result.get('tokens', [])[:5]:
                balance_text += f"• {token['symbol']}: {token['balance']} (${token['usd']:.2f})\n"
            
            await update.message.reply_text(balance_text, parse_mode='Markdown')
        except Exception as e:
            await update.message.reply_text(f'❌ Error: {str(e)}')
    
    async def swap(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Swap tokens"""
        if len(context.args) < 3:
            await update.message.reply_text('Usage: /swap <amount> <from> <to>\nExample: `/swap 0.1 ETH USDC`', parse_mode='Markdown')
            return
        
        amount = context.args[0]
        from_token = context.args[1].upper()
        to_token = context.args[2].upper()
        
        agent = self.get_or_create_agent(update.effective_user.id)
        
        await update.message.reply_text(f'⏳ Swapping {amount} {from_token} → {to_token}...')
        
        try:
            # Get quote first
            quote = await agent.get_swap_quote(from_token, to_token, float(amount))
            
            keyboard = [
                [
                    InlineKeyboardButton("✅ Confirm", callback_data=f"swap_confirm_{amount}_{from_token}_{to_token}"),
                    InlineKeyboardButton("❌ Cancel", callback_data="swap_cancel"),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"""
💱 **Swap Quote**

**From:** {amount} {from_token}
**To:** ~{quote['output']:.6f} {to_token}
**Price Impact:** {quote['price_impact']:.2f}%
**Gas:** ~${quote['gas_usd']:.2f}

Confirm swap?
""",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
        except Exception as e:
            await update.message.reply_text(f'❌ Error: {str(e)}')
    
    async def swap_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle swap confirmation"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "swap_cancel":
            await query.edit_message_text("❌ Swap cancelled")
            return
        
        if query.data.startswith("swap_confirm_"):
            parts = query.data.split("_")
            amount, from_token, to_token = parts[2], parts[3], parts[4]
            
            agent = self.get_or_create_agent(query.from_user.id)
            
            await query.edit_message_text(f'⏳ Executing swap {amount} {from_token} → {to_token}...')
            
            try:
                result = await agent.swap(from_token, to_token, float(amount))
                
                await query.edit_message_text(
                    f"""
✅ **Swap Complete!**

**TX Hash:** `{result['tx_hash']}`
**From:** {amount} {from_token}
**To:** {result['output']:.6f} {to_token}
**Gas Used:** ${result['gas_usd']:.2f}

[View on Explorer]({result['explorer_url']})
""",
                    parse_mode='Markdown'
                )
            except Exception as e:
                await query.edit_message_text(f'❌ Swap failed: {str(e)}')
    
    async def portfolio(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """View portfolio"""
        agent = self.get_or_create_agent(update.effective_user.id)
        
        await update.message.reply_text('⏳ Loading portfolio...')
        
        try:
            result = await agent.get_portfolio()
            
            pnl_emoji = "📈" if result['pnl'] >= 0 else "📉"
            
            portfolio_text = f"""
📊 **Portfolio Overview**

**Total Value:** ${result['total_value']:.2f}
**24h Change:** {pnl_emoji} {result['pnl_percent']:.2f}%
**P&L:** ${result['pnl']:.2f}

**Holdings:**
"""
            for holding in result.get('holdings', [])[:10]:
                change = "🟢" if holding['change_24h'] >= 0 else "🔴"
                portfolio_text += f"• {holding['symbol']}: ${holding['value']:.2f} {change} {holding['change_24h']:.1f}%\n"
            
            await update.message.reply_text(portfolio_text, parse_mode='Markdown')
        except Exception as e:
            await update.message.reply_text(f'❌ Error: {str(e)}')
    
    async def snipe(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Monitor new pairs"""
        if not context.args:
            await update.message.reply_text('Usage: /snipe <token_address>\nExample: `/snipe 0x1234...`', parse_mode='Markdown')
            return
        
        token = context.args[0]
        agent = self.get_or_create_agent(update.effective_user.id)
        
        await update.message.reply_text(f'🎯 Monitoring {token}...')
        
        try:
            info = await agent.get_token_info(token)
            
            safety = "🟢 Safe" if info['is_safe'] else "🔴 Risky"
            
            await update.message.reply_text(
                f"""
🔍 **Token Info**

**Name:** {info['name']} ({info['symbol']})
**Price:** ${info['price']:.8f}
**Liquidity:** ${info['liquidity']:,.0f}
**Safety:** {safety}

**Checks:**
• Honeypot: {'❌' if info['is_honeypot'] else '✅'}
• Mint Auth: {'❌' if info['has_mint'] else '✅'}
• LP Locked: {'✅' if info['lp_locked'] else '❌'}

Use `/swap 0.01 ETH {info['symbol']}` to buy
""",
                parse_mode='Markdown'
            )
        except Exception as e:
            await update.message.reply_text(f'❌ Error: {str(e)}')
    
    async def bridge(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Bridge assets"""
        if len(context.args) < 3:
            await update.message.reply_text(
                'Usage: /bridge <amount> <token> <chain>\nExample: `/bridge 100 USDC arbitrum`',
                parse_mode='Markdown'
            )
            return
        
        amount = context.args[0]
        token = context.args[1].upper()
        dest_chain = context.args[2].lower()
        
        agent = self.get_or_create_agent(update.effective_user.id)
        
        await update.message.reply_text(f'⏳ Finding best route for {amount} {token} → {dest_chain}...')
        
        try:
            route = await agent.get_bridge_quote(token, float(amount), dest_chain)
            
            keyboard = [
                [
                    InlineKeyboardButton("✅ Bridge", callback_data=f"bridge_confirm_{amount}_{token}_{dest_chain}"),
                    InlineKeyboardButton("❌ Cancel", callback_data="bridge_cancel"),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"""
🌉 **Bridge Quote**

**From:** {amount} {token} ({route['from_chain']})
**To:** {dest_chain}
**You'll receive:** ~{route['output']:.2f} {token}
**Fee:** ${route['fee']:.2f}
**Time:** ~{route['time_minutes']} min
**Route:** {route['provider']}

Confirm bridge?
""",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
        except Exception as e:
            await update.message.reply_text(f'❌ Error: {str(e)}')
    
    async def bridge_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle bridge confirmation"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "bridge_cancel":
            await query.edit_message_text("❌ Bridge cancelled")
            return
        
        if query.data.startswith("bridge_confirm_"):
            parts = query.data.split("_")
            amount, token, dest_chain = parts[2], parts[3], parts[4]
            
            agent = self.get_or_create_agent(query.from_user.id)
            
            await query.edit_message_text(f'⏳ Bridging {amount} {token} to {dest_chain}...')
            
            try:
                result = await agent.bridge(token, float(amount), dest_chain)
                
                await query.edit_message_text(
                    f"""
✅ **Bridge Initiated!**

**TX Hash:** `{result['tx_hash']}`
**Amount:** {amount} {token}
**Destination:** {dest_chain}
**ETA:** ~{result['eta_minutes']} min

[View on Explorer]({result['explorer_url']})
""",
                    parse_mode='Markdown'
                )
            except Exception as e:
                await query.edit_message_text(f'❌ Bridge failed: {str(e)}')
    
    async def chain(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Switch chain"""
        if not context.args:
            chains = ", ".join(self.chains.keys())
            await update.message.reply_text(f'Usage: /chain <name>\nAvailable: {chains}')
            return
        
        chain_name = context.args[0].lower()
        
        if chain_name not in self.chains:
            await update.message.reply_text(f'❌ Unknown chain: {chain_name}')
            return
        
        agent = self.get_or_create_agent(update.effective_user.id, chain_name)
        await update.message.reply_text(f'✅ Switched to {chain_name}')
    
    async def help_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show help"""
        await self.start(update, context)


def main():
    """Start the bot"""
    if BOT_TOKEN == 'YOUR_BOT_TOKEN':
        print("❌ Set TELEGRAM_BOT_TOKEN in .env first!")
        return
    
    bot = Web3Bot()
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Command handlers
    app.add_handler(CommandHandler("start", bot.start))
    app.add_handler(CommandHandler("help", bot.help_cmd))
    app.add_handler(CommandHandler("balance", bot.balance))
    app.add_handler(CommandHandler("swap", bot.swap))
    app.add_handler(CommandHandler("portfolio", bot.portfolio))
    app.add_handler(CommandHandler("snipe", bot.snipe))
    app.add_handler(CommandHandler("bridge", bot.bridge))
    app.add_handler(CommandHandler("chain", bot.chain))
    
    # Callback handlers
    app.add_handler(CallbackQueryHandler(bot.swap_callback, pattern="^swap_"))
    app.add_handler(CallbackQueryHandler(bot.bridge_callback, pattern="^bridge_"))
    
    # Start polling
    print("🤖 Web3 Agent Bot started!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
