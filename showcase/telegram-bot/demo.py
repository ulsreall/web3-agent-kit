#!/usr/bin/env python3
"""
Demo script for web3-agent-kit
Simulates bot interactions for recording GIF
"""

import time
import sys

def print_slow(text, delay=0.03):
    """Print text with typing effect"""
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(delay)
    print()

def demo():
    """Run demo sequence"""
    print("\033[1;36m")  # Cyan
    
    print_slow("🤖 Web3 Agent Kit — Telegram Bot Demo", 0.05)
    print()
    time.sleep(1)
    
    # Balance check
    print_slow("👤 User: /balance", 0.05)
    time.sleep(0.5)
    print()
    print_slow("🤖 Bot: ⏳ Checking balance...", 0.03)
    time.sleep(1)
    print()
    print_slow("💰 Wallet Balance", 0.03)
    print_slow("━━━━━━━━━━━━━━━━━━━━", 0.01)
    print_slow("Native: 1.5 ETH", 0.03)
    print_slow("USD Value: $4,500.00", 0.03)
    print()
    print_slow("Top Tokens:", 0.03)
    print_slow("• USDC: 1,000.00 ($1,000.00)", 0.03)
    print_slow("• UNI: 50.0 ($350.00)", 0.03)
    print_slow("• LINK: 25.0 ($250.00)", 0.03)
    
    time.sleep(2)
    print()
    
    # Swap
    print_slow("👤 User: /swap 0.1 ETH USDC", 0.05)
    time.sleep(0.5)
    print()
    print_slow("🤖 Bot: ⏳ Getting quote...", 0.03)
    time.sleep(1)
    print()
    print_slow("💱 Swap Quote", 0.03)
    print_slow("━━━━━━━━━━━━━━━━━━━━", 0.01)
    print_slow("From: 0.1 ETH", 0.03)
    print_slow("To: ~300.00 USDC", 0.03)
    print_slow("Price Impact: 0.01%", 0.03)
    print_slow("Gas: ~$5.00", 0.03)
    print()
    print_slow("[✅ Confirm] [❌ Cancel]", 0.03)
    
    time.sleep(2)
    print()
    
    # Confirm
    print_slow("👤 User: ✅ Confirm", 0.05)
    time.sleep(0.5)
    print()
    print_slow("🤖 Bot: ⏳ Executing swap...", 0.03)
    time.sleep(2)
    print()
    print_slow("✅ Swap Complete!", 0.03)
    print_slow("━━━━━━━━━━━━━━━━━━━━", 0.01)
    print_slow("TX: 0xabc...def", 0.03)
    print_slow("From: 0.1 ETH", 0.03)
    print_slow("To: 300.00 USDC", 0.03)
    print_slow("Gas: $4.50", 0.03)
    
    time.sleep(2)
    print()
    
    # Token snipe
    print_slow("👤 User: /snipe 0x1234...5678", 0.05)
    time.sleep(0.5)
    print()
    print_slow("🤖 Bot: ⏳ Analyzing token...", 0.03)
    time.sleep(1)
    print()
    print_slow("🔍 Token Info", 0.03)
    print_slow("━━━━━━━━━━━━━━━━━━━━", 0.01)
    print_slow("Name: SafeMoon (SAFEMOON)", 0.03)
    print_slow("Price: $0.00000100", 0.03)
    print_slow("Liquidity: $50,000", 0.03)
    print_slow("Safety: 🟢 Safe", 0.03)
    print()
    print_slow("Checks:", 0.03)
    print_slow("• Honeypot: ✅", 0.03)
    print_slow("• Mint Auth: ✅", 0.03)
    print_slow("• LP Locked: ✅", 0.03)
    
    time.sleep(2)
    print()
    
    # Bridge
    print_slow("👤 User: /bridge 100 USDC arbitrum", 0.05)
    time.sleep(0.5)
    print()
    print_slow("🤖 Bot: ⏳ Finding best route...", 0.03)
    time.sleep(1)
    print()
    print_slow("🌉 Bridge Quote", 0.03)
    print_slow("━━━━━━━━━━━━━━━━━━━━", 0.01)
    print_slow("From: 100 USDC (Ethereum)", 0.03)
    print_slow("To: Arbitrum", 0.03)
    print_slow("You'll receive: ~99.50 USDC", 0.03)
    print_slow("Fee: $0.50", 0.03)
    print_slow("Time: ~5 min", 0.03)
    print_slow("Route: Li.Fi", 0.03)
    print()
    print_slow("[✅ Bridge] [❌ Cancel]", 0.03)
    
    print()
    print_slow("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", 0.01)
    print_slow("⭐ github.com/ulsreall/web3-agent-kit", 0.05)
    print_slow("📦 pip install web3-agent-kit", 0.05)
    print()
    
    print("\033[0m")  # Reset

if __name__ == '__main__':
    demo()
