# ADR-003: Multi-Source Oracle with Weighted Median

**Status:** Accepted  
**Date:** 2026-07-23  
**Context:** Price data is critical for swaps, portfolio valuation, and security checks. Single-source oracles have single points of failure.  
**Decision:** The OracleAggregator fetches from Chainlink (on-chain), DexScreener, and CoinGecko (off-chain), then computes a weighted median. No single source can dominate the price.  
**Consequences:**  
- ✅ Resistant to a single source failing or returning manipulated data  
- ❌ Median is slower than a single API call  
- ❌ DexScreener and CoinGecko rate limits affect throughput at scale