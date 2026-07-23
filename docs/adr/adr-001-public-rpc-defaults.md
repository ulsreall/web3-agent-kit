# ADR-001: Default to Public RPC Endpoints

**Status:** Accepted  
**Date:** 2026-07-23  
**Context:** Users need blockchain access out of the box without configuring infrastructure.  
**Decision:** The kit defaults to public RPC endpoints (LlamaNodes, Ankr, public DRC) for all supported chains.  
**Consequences:**  
- ✅ Zero-config setup for new users  
- ❌ Rate-limited (heavier use needs a private RPC)  
- ❌ Public RPCs can return stale or manipulated data for some queries