# ADR-002: Builder Pattern Without Execution

**Status:** Accepted  
**Date:** 2026-07-23  
**Context:** Several DeFi methods (swap, mint position) return a parameter dict instead of executing immediately.  
**Decision:** The kit uses a "build → sign → execute" pattern where methods build transaction parameters without broadcasting. This separates concerns: the Agent/API layer decides when to sign and send.  
**Consequences:**  
- ✅ User can inspect, simulate, or modify params before execution  
- ❌ Extra step confuses users expecting a single "do it" call  
- ❌ Some callers forget to execute the built transaction