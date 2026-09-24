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
        - from_keystore
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
### Create from Keystore File
```python
# Standard Ethereum JSON (V3/UTC) keystore file, e.g. exported from geth/Parity
wallet = Wallet.from_keystore("path/to/keystore.json", password="your-password", chain_manager=chain_manager)
```
### Check Balance
```python
balance = wallet.get_balance(Chain.BASE)
print(f"Balance: {balance} ETH")
```
### Sign and Send Transaction

Wallet signing **fails closed** unless a `PreSignInterceptor` is bound. Before enabling writes, your application must configure an `ExecutionPolicy` and a real `AuthorizationProvider` that independently verifies a fresh, single-use principal authorization; operator confirmation alone does not satisfy this requirement.

```python
from web3_agent_kit.execution import ActionType, PreSignInterceptor

# `policy` and `application_authorization_provider` must be configured by your app.
wallet.bind_enforcement(
    PreSignInterceptor(
        policy=policy,
        signer=wallet._raw_signer,
        authorization_provider=application_authorization_provider,
    )
)

# The transaction must be fully built (including from, nonce, and chainId).
signed = wallet.sign_transaction(tx_dict, Chain.BASE, action=ActionType.CONTRACT_CALL)
tx_hash = wallet.send_transaction(tx_dict, Chain.BASE, action=ActionType.CONTRACT_CALL)
```

The current authorization fingerprint does not include gas-limit or fee fields. Do not treat it as a commitment to maximum transaction cost; see the [safety pipeline](../safety-and-transaction-pipeline.md).

---
## Security Notes
!!! warning "Private Key Security"
    Never hardcode private keys in source code. Always use environment variables
    or secure key management systems.
- Private keys are stored in memory only
- Never logged or serialized
- Use `Wallet.from_env()` for production code
