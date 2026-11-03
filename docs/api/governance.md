# Governance Module

The module exposes `GovernanceTracker` for reading proposals and voting power,
and for delegating tokens.

```python
from web3_agent_kit.governance import GovernanceTracker

tracker = GovernanceTracker(rpc_url="https://eth.example-rpc.com")
proposals = tracker.get_active_proposals(dao="uniswap", limit=10)
power = tracker.get_voting_power(address="0x...", dao="uniswap")
print(proposals, power.power)
```

`GovernanceTracker` requires an RPC URL. `get_active_proposals` accepts a known
DAO name or `governor_address`; `get_voting_power` accepts a token address or a
known DAO name. `delegate(delegatee, token, private_key)` broadcasts a
delegation transaction and requires the configured signing authorization
pipeline. Voting submission is not implemented. The package does not expose
`SnapshotVoter`, `TallyTracker`, or `DelegationManager` classes.
