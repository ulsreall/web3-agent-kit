# Account Abstraction (ERC-4337)

The account-abstraction module contains a smart-account helper, paymaster
configuration, and UserOperation data types. UserOperations encode calls using
the SimpleAccount v7 `execute(address,uint256,bytes)` interface and fetch the
EntryPoint nonce before submission.

## `AAWallet`

Construct a wallet with an RPC endpoint. The factory can be a key in
`KNOWN_FACTORIES` (for example, `simple_account_v7`) or a factory address.
Submission requires an external `signer` callback, which receives the fully
prepared operation, EntryPoint address, and chain ID. Without a signer callback,
no operation is submitted. Call encoding for Safe, Kernel, and custom account
factories is not implemented; those factories raise `NotImplementedError`.

```python
from web3_agent_kit.account_abstraction import AAWallet

wallet = AAWallet(
    rpc_url="https://base.example-rpc.com",
    chain="base",
    factory="simple_account_v7",
)
address = wallet.get_counterfactual_address(owner="0x...")
info = wallet.deploy_account(owner="0x...")
print(info.address, info.deployed)
```

`deploy_account` currently computes the account address and checks whether code
exists; it does not deploy the account. `send_user_op(to, value=0, data="0x",
sender=None, owner=None, signer=...)` submits a UserOperation to the configured
bundler and therefore can initiate an on-chain action. Use only after
configuring and reviewing the account, owner, and transaction parameters.

## `AAPaymaster` and `UserOperation`

`AAPaymaster(paymaster_type="verifying", url=None, policy_id=None, api_key=None)`
configures sponsorship. Verifying sponsorship makes an external request and
requires the paymaster URL and API key. `UserOperation` is the package's
dataclass representation of an ERC-4337 operation.

The package does not expose a `BundlerClient` or `AccountFactory` class.
