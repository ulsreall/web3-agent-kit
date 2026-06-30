# Account Abstraction (ERC-4337)

Smart contract wallet support via ERC-4337.

## Classes

### `BundlerClient`

Submit UserOperations to bundler.

### `PaymasterClient`

Gas sponsorship via paymaster.

### `AccountFactory`

Deploy smart accounts: SimpleAccount, Safe, Kernel.

```python
from web3_agent_kit.account_abstraction import BundlerClient

bundler = BundlerClient(url="https://...", chain_id=8453)
op = bundler.build_user_op(sender=addr, call_data=calldata)
bundler.send_user_op(op)
```
