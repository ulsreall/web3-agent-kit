# I Found a Safety Gate That Was Never Connected — Here's How I Caught It

**Draft for Hacker News / Reddit.**

---

I maintain [Web3 Agent Kit](https://github.com/ulsreall/web3-agent-kit), an open-source Python framework for AI agents that interact with blockchains. The kit includes a `SpendGovernor` — a safety gate that's supposed to limit how much an autonomous agent can spend per transaction, per day, and per session.

Or so I thought.

During a self-audit, I found that the `confirm_fn` parameter — the callback that lets a human operator approve or reject each transaction — was **never connected to the governor**. You could set `confirm_fn=my_approval_function` on the `AgentConfig`, but the governor would happily authorize transactions without ever calling it.

The code looked correct at first glance. The `AgentConfig` had a `confirm_fn` field. The `SpendGovernor` had a `confirm_fn` field. But there was no wiring between them. The config field existed, the governor field existed, but the data flow was broken.

## How I found it

Not through static analysis or a fancy tool — I traced the `_act()` method manually when writing tests. The test was supposed to verify that `confirm_fn` gets called before transaction execution. It never fired.

## The fix

Three changes:
1. `SpendGovernor.__init__` now raises `ValueError` if `require_confirm=True` is set without a `confirm_fn` (fail closed)
2. `Agent.__init__` now pipes `config.confirm_fn` into the governor
3. A secondary issue: `_estimate_tx_value` returned `0.0` for unrecognized argument keys, silently approving unknown-value actions. Changed to return `None` (block unknown values).

## Lesson

Self-audits are uncomfortable because you find your own mistakes. But they're worth it. Every safety feature in this kit now has a test proving it works — not just that the field exists.

The full audit results are in `CHANGELOG.md` under v1.15.0.

---

*[Draft for review. Tone: honest, not self-promotional. Focus on the bug, not the project.]*