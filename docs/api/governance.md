# Governance Module

DAO voting, proposals, and delegation.

## Classes

### `SnapshotVoter`

Vote on Snapshot proposals.

### `TallyTracker`

Track on-chain governance proposals.

### `DelegationManager`

Manage token delegation.

```python
from web3_agent_kit.governance import SnapshotVoter

voter = SnapshotVoter(space="aave.eth")
proposals = voter.get_proposals(status="active")
voter.vote(proposal_id="Qm...", choice=1)
```
