# Wallet
Wallet management — secure key handling and transaction signing.
The `Wallet` class handles private key management, transaction signing,
and balance queries across multiple chains.
---
## Classes

      members:
        - from_key
        - from_env
        - from_seed
        - address
        - private_key
        - get_balance
        - sign_transaction
        - send_transaction
      show_root_heading: true
      show_source: true
---

      show_root_heading: true
      show_source: true
---
## Usage
### Create from Environment Variable
```python
from web3_agent_kit import Wallet, ChainManager, Chain
chain_manager = ChainManager(chains=[Chain.BASE, Chain.ETHEREUM])
wallet = Wallet.from_env("PRIVATE_KEY", chain_manager=chain_manager)
print(f"Address: {wallet.address}")
```
### Create from Private Key
```python
wallet = Wallet.from_key("0x...", chain_manager=chain_manager)
```
### Create from Seed Phrase
```python
wallet = Wallet.from_seed("word1 word2 ... word12", chain_manager=chain_manager)
```
### Check Balance
```python
balance = wallet.get_balance(Chain.BASE)
print(f"Balance: {balance} ETH")
```
### Sign and Send Transaction
```python
# Sign only
signed = wallet.sign_transaction(tx_dict, Chain.BASE)
# Sign and send
tx_hash = wallet.send_transaction(tx_dict, Chain.BASE)
print(f"TX: {tx_hash}")
```
---
## Security Notes
!!! warning "Private Key Security"
    Never hardcode private keys in source code. Always use environment variables
    or secure key management systems.
- Private keys are stored in memory only
- Never logged or serialized
- Use `Wallet.from_env()` for production code
